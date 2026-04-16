"""LiteLLM-based model router for ADP.

Implements ADR-002:
  - Route tasks to assigned model (gemini/claude/codex)
  - Automatic fallback: primary → secondary → tertiary (max 2 fallbacks)
  - Mandatory agent_sessions logging for every invocation
  - Classified error handling: timeout, rate_limit, api_error, unknown

Usage:
    router = ModelRouter()
    result = await router.route_task(
        task_id=uuid.UUID("..."),
        model_assigned="claude",
        prompt="Implement a FastAPI endpoint for...",
        db=db_session,  # optional; required for agent_sessions logging
    )
    print(result.content)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import litellm
from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.schemas import AgentModel, AgentSession, SessionStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """Successful completion from a model."""
    content: str
    model_used: str           # LiteLLM model string (e.g. "claude-sonnet-4-6")
    model_assigned: str       # Original AgentModel value ("claude" / "gemini" / "codex")
    tokens_input: int
    tokens_output: int
    tokens_total: int
    latency_ms: int
    attempt: int              # 1 = primary succeeded, 2+ = fallback was used
    session_id: Optional[uuid.UUID] = None


@dataclass
class RouterError:
    """Structured error from the router (all attempts exhausted)."""
    error_type: str           # timeout | rate_limit | auth | api_error | unknown
    message: str
    model_assigned: str
    attempts: int
    last_model_tried: str


class ModelRouterError(Exception):
    """Raised when all fallback attempts are exhausted."""
    def __init__(self, details: RouterError) -> None:
        super().__init__(details.message)
        self.details = details


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------

def _classify_error(exc: Exception) -> str:
    if isinstance(exc, Timeout):
        return "timeout"
    if isinstance(exc, RateLimitError):
        return "rate_limit"
    if isinstance(exc, AuthenticationError):
        return "auth"
    if isinstance(exc, (APIConnectionError, ServiceUnavailableError, BadRequestError)):
        return "api_error"
    return "unknown"


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class ModelRouter:
    """Routes tasks to LLM models with automatic fallback and session logging.

    Thread-safe; share a single instance across the application.
    DB session is passed per-call (not stored on the instance) to support
    both request-scoped and background task usage patterns.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._configure_litellm()
        logger.info(
            "ModelRouter initialized | claude=%s gemini=%s codex=%s",
            self._settings.claude_model,
            self._settings.gemini_model,
            self._settings.codex_model,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route_task(
        self,
        task_id: uuid.UUID,
        model_assigned: str,         # AgentModel value: "claude" | "gemini" | "codex"
        prompt: str,
        system_prompt: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> RouteResult:
        """Route a prompt to the assigned model with automatic fallback.

        Args:
            task_id:        UUID of the task (for agent_sessions FK).
            model_assigned: AgentModel value from the task record.
            prompt:         User-role message to send to the model.
            system_prompt:  Optional system-role message (role definition).
            db:             AsyncSession for logging to agent_sessions.
                            If None, logging is skipped (dry-run / test mode).
            temperature:    Sampling temperature (default 0.2 for determinism).
            max_tokens:     Maximum output tokens.

        Returns:
            RouteResult with content, token counts, latency, and attempt number.

        Raises:
            ModelRouterError: When all fallback attempts are exhausted.
        """
        chain = self._settings.get_fallback_chain(model_assigned)
        last_exc: Optional[Exception] = None
        last_model = chain[0]

        for attempt_idx, model in enumerate(chain):
            last_model = model
            logger.info(
                "route_task | task=%s assigned=%s attempt=%d model=%s",
                task_id, model_assigned, attempt_idx + 1, model,
            )
            try:
                result = await self._call_model(
                    task_id=task_id,
                    model=model,
                    model_assigned=model_assigned,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    attempt=attempt_idx + 1,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    db=db,
                )
                return result

            except ModelRouterError:
                # Already logged; re-raise auth errors immediately (no fallback)
                raise
            except Exception as exc:
                error_type = _classify_error(exc)
                last_exc = exc

                logger.warning(
                    "route_task | task=%s model=%s attempt=%d error_type=%s msg=%s",
                    task_id, model, attempt_idx + 1, error_type, str(exc),
                )

                # Auth errors: fallback won't help — fail immediately
                if error_type == "auth":
                    await self._log_failed_session(
                        task_id=task_id,
                        model_assigned=model_assigned,
                        model_version=model,
                        error_type=error_type,
                        error_message=str(exc),
                        db=db,
                    )
                    raise ModelRouterError(
                        RouterError(
                            error_type=error_type,
                            message=f"Authentication failed for model {model}: {exc}",
                            model_assigned=model_assigned,
                            attempts=attempt_idx + 1,
                            last_model_tried=model,
                        )
                    ) from exc

                # Log failed attempt; loop continues to next fallback
                await self._log_failed_session(
                    task_id=task_id,
                    model_assigned=model_assigned,
                    model_version=model,
                    error_type=error_type,
                    error_message=str(exc),
                    db=db,
                )

                if attempt_idx < len(chain) - 1:
                    logger.info(
                        "route_task | task=%s falling back to %s",
                        task_id, chain[attempt_idx + 1],
                    )

        # All attempts exhausted
        error_type = _classify_error(last_exc) if last_exc else "unknown"
        raise ModelRouterError(
            RouterError(
                error_type=error_type,
                message=f"All {len(chain)} model attempts failed. Last: {last_exc}",
                model_assigned=model_assigned,
                attempts=len(chain),
                last_model_tried=last_model,
            )
        ) from last_exc

    async def health_check(self) -> dict[str, dict]:
        """Dry-run each configured model with a minimal prompt.

        Returns a dict of {model_key: {status, latency_ms, error}}.
        Does NOT write to DB (no task_id context).
        """
        results: dict[str, dict] = {}
        checks = {
            "claude": self._settings.claude_model,
            "gemini": self._settings.gemini_model,
            "codex": self._settings.codex_model,
        }
        for key, model in checks.items():
            try:
                start = time.monotonic()
                resp = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with the single word: OK"}],
                    max_tokens=5,
                    timeout=15,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                results[key] = {
                    "status": "ok",
                    "latency_ms": latency_ms,
                    "response": resp.choices[0].message.content.strip(),
                    "model": model,
                    "error": None,
                }
                logger.info("health_check | %s (%s) OK %dms", key, model, latency_ms)
            except Exception as exc:
                results[key] = {
                    "status": "error",
                    "latency_ms": None,
                    "response": None,
                    "model": model,
                    "error": f"{_classify_error(exc)}: {exc}",
                }
                logger.warning("health_check | %s (%s) FAILED: %s", key, model, exc)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _configure_litellm(self) -> None:
        """Set LiteLLM provider keys from settings (never from code literals)."""
        s = self._settings
        if s.anthropic_api_key:
            litellm.anthropic_key = s.anthropic_api_key
        if s.google_api_key:
            litellm.google_key = s.google_api_key
        if s.openai_api_key:
            litellm.openai_key = s.openai_api_key

        # Suppress LiteLLM internal verbose logging; our logger handles it
        litellm.suppress_debug_info = True
        litellm.set_verbose = False

    async def _call_model(
        self,
        task_id: uuid.UUID,
        model: str,
        model_assigned: str,
        prompt: str,
        system_prompt: Optional[str],
        attempt: int,
        temperature: float,
        max_tokens: int,
        db: Optional[AsyncSession],
    ) -> RouteResult:
        """Execute a single model call and log the session."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.monotonic()
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self._settings.request_timeout_s,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage or {}
        tokens_input = getattr(usage, "prompt_tokens", 0) or 0
        tokens_output = getattr(usage, "completion_tokens", 0) or 0
        tokens_total = getattr(usage, "total_tokens", tokens_input + tokens_output) or 0

        content = response.choices[0].message.content or ""

        session_id = await self._log_success_session(
            task_id=task_id,
            model_assigned=model_assigned,
            model_version=model,
            tokens_used=tokens_total,
            latency_ms=latency_ms,
            db=db,
        )

        logger.info(
            "route_task | task=%s model=%s tokens=%d latency=%dms attempt=%d OK",
            task_id, model, tokens_total, latency_ms, attempt,
        )

        return RouteResult(
            content=content,
            model_used=model,
            model_assigned=model_assigned,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_total=tokens_total,
            latency_ms=latency_ms,
            attempt=attempt,
            session_id=session_id,
        )

    async def _log_success_session(
        self,
        task_id: uuid.UUID,
        model_assigned: str,
        model_version: str,
        tokens_used: int,
        latency_ms: int,
        db: Optional[AsyncSession],
    ) -> Optional[uuid.UUID]:
        if db is None:
            return None
        try:
            # Map LiteLLM model string back to AgentModel enum value
            agent_model_val = self._resolve_agent_model(model_assigned)
            session = AgentSession(
                task_id=task_id,
                model_used=agent_model_val,
                model_version=model_version,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                status=SessionStatus.completed,
                error_message=None,
            )
            db.add(session)
            await db.flush()
            return session.id
        except Exception as exc:
            # Logging failure must NEVER break the main flow
            logger.error("Failed to log agent_session (success): %s", exc)
            return None

    async def _log_failed_session(
        self,
        task_id: uuid.UUID,
        model_assigned: str,
        model_version: str,
        error_type: str,
        error_message: str,
        db: Optional[AsyncSession],
    ) -> None:
        if db is None:
            return
        try:
            agent_model_val = self._resolve_agent_model(model_assigned)
            session = AgentSession(
                task_id=task_id,
                model_used=agent_model_val,
                model_version=model_version,
                tokens_used=None,
                latency_ms=None,
                status=SessionStatus.failed if error_type != "timeout" else SessionStatus.timeout,
                error_message=f"[{error_type}] {error_message}"[:2000],
            )
            db.add(session)
            await db.flush()
        except Exception as exc:
            logger.error("Failed to log agent_session (failure): %s", exc)

    @staticmethod
    def _resolve_agent_model(model_assigned: str) -> AgentModel:
        """Map model_assigned string to AgentModel enum, defaulting to claude."""
        try:
            return AgentModel(model_assigned)
        except ValueError:
            logger.warning("Unknown model_assigned '%s', defaulting to claude", model_assigned)
            return AgentModel.claude


# ---------------------------------------------------------------------------
# Module-level singleton — import and reuse across the app
# ---------------------------------------------------------------------------

_router_instance: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    """Return the module-level ModelRouter singleton.

    Initialised lazily on first call. Safe to call from FastAPI lifespan
    or dependency injection.
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance
