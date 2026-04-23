"""SmartRouter — Intelligent task parallelization orchestrator for ADP."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.middleware.audit_logger import sanitize_body
from app.models.schemas import AgentModel, AgentSession, RoutingDecision

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public enums and dataclasses
# ---------------------------------------------------------------------------


class ExecutionMode(Enum):
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    AUTOMATED = "automated"


@dataclass
class ComponentAnalysis:
    name: str
    type: str  # "parallel" | "sequential"
    depends_on: List[str]
    estimated_duration_min: float
    recommended_model: str


@dataclass
class ExecutionPlan:
    task_id: str
    estimated_total_duration_min: float
    estimated_cost_usd: float
    components: List[ComponentAnalysis]
    critical_path_component: str
    parallel_components: List[str]
    sequential_components: List[str]
    premium_suggestion: Optional[Dict]
    timeline_visualization: str


@dataclass
class ComponentResult:
    name: str
    success: bool
    duration_min: float
    cost_usd: float
    model_used: str
    output: str
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    success: bool
    actual_duration_min: float
    actual_cost_usd: float
    failures: List[Dict]
    parallelization_breakdown: Dict
    execution_log: str
    suggestions: List[str]


@dataclass
class RoutingResult:
    """Result of dynamic routing for a single task."""
    content: str
    model_used: str
    provider_model: str
    latency_ms: int
    tokens_used: int
    attempts: int
    reasoning: str
    success: bool = True


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Approximate cost per component call (2k input tokens + 3k output tokens)
_COST_PER_COMPONENT: Dict[str, float] = {
    "claude": (2_000 * 3.0 + 3_000 * 15.0) / 1_000_000,    # ~$0.051
    "gemini": (2_000 * 0.35 + 3_000 * 1.40) / 1_000_000,   # ~$0.0049
    "codex":  (2_000 * 2.5 + 3_000 * 10.0) / 1_000_000,    # ~$0.035
}

_PREMIUM_MODELS: Dict[str, str] = {
    "claude": "claude-opus-4-7",
    "gemini": "gemini-2.5-pro",
    "codex":  "gpt-4o",
}

_PREMIUM_SPEEDUP = 1.5          # Premium models ~1.5× faster on complex tasks
_PREMIUM_THRESHOLD_MIN = 7.0    # Suggest premium when critical path > this
_BUFFER_FACTOR = 1.20           # 20% safety buffer on all time estimates
_PARALLEL_DELAY_S = 0.5         # Stagger between parallel task launches

_COMPONENT_PATTERNS: Dict[str, Dict] = {
    "Backend API": {
        "keywords": {"api", "rest", "endpoint", "route", "fastapi", "backend", "server", "crud", "http", "express"},
        "model": "claude",
        "base_duration_min": 8.0,
        "depends_on": [],
    },
    "Frontend": {
        "keywords": {"react", "dashboard", "ui", "frontend", "interface", "component", "typescript", "tailwind", "vite", "vue", "angular"},
        "model": "gemini",
        "base_duration_min": 6.0,
        "depends_on": [],
    },
    "Database": {
        "keywords": {"schema", "migration", "model", "database", "db", "sql", "table", "sqlalchemy", "postgres", "mongodb"},
        "model": "claude",
        "base_duration_min": 4.0,
        "depends_on": [],
    },
    "Tests": {
        "keywords": {"test", "unit test", "pytest", "coverage", "spec", "testing", "mock", "e2e"},
        "model": "codex",
        "base_duration_min": 5.0,
        "depends_on": ["Backend API", "Frontend"],
    },
    "Documentation": {
        "keywords": {"doc", "swagger", "readme", "documentation", "openapi", "apidoc"},
        "model": "codex",
        "base_duration_min": 3.0,
        "depends_on": ["Backend API"],
    },
    "Security": {
        "keywords": {"security", "auth", "authentication", "authorization", "owasp", "encryption", "jwt", "oauth"},
        "model": "codex",
        "base_duration_min": 4.0,
        "depends_on": ["Backend API"],
    },
    "Deployment": {
        "keywords": {"deploy", "ci/cd", "docker", "infrastructure", "kubernetes", "vercel", "railway", "pipeline", "cicd"},
        "model": "claude",
        "base_duration_min": 3.0,
        "depends_on": ["Tests"],
    },
}

_COMPLEXITY_KEYWORDS_HIGH = {"complex", "enterprise", "large", "full", "complete", "comprehensive"}
_COMPLEXITY_KEYWORDS_LOW = {"simple", "basic", "minimal", "small", "quick"}

_TASK_TYPE_TO_MODEL: Dict[str, str] = {
    "frontend": "gemini-2.0-flash",
    "backend": "claude-opus",
    "testing": "gpt-4o",
    "integration": "claude-opus",
    "security": "gpt-4o",
}

_MODEL_LABEL_TO_AGENT: Dict[str, str] = {
    "claude-opus": "claude",
    "gemini-2.0-flash": "gemini",
    "gpt-4o": "codex",
}

_MODEL_LABEL_DISPLAY: Dict[str, str] = {
    "claude-opus": "Claude",
    "gemini-2.0-flash": "Gemini",
    "gpt-4o": "Codex",
}

_FALLBACK_CHAINS: Dict[str, List[str]] = {
    "backend": ["claude-opus", "gemini-2.0-flash", "gpt-4o"],
    "frontend": ["gemini-2.0-flash", "claude-opus", "gpt-4o"],
    "testing": ["gpt-4o", "claude-opus", "gemini-2.0-flash"],
    "integration": ["claude-opus", "gemini-2.0-flash", "gpt-4o"],
    "security": ["gpt-4o", "claude-opus", "gemini-2.0-flash"],
}


def _sanitize_reasoning(reasoning: str) -> str:
    sanitized = sanitize_body({"reasoning": reasoning})
    return str(sanitized.get("reasoning", reasoning))


async def write_routing_decision(
    *,
    task_id: str,
    task_type: str,
    chosen_model: str,
    reasoning: str,
    latency_ms: int,
    success: bool,
) -> None:
    """Persist one routing decision using a fresh DB session. Failures are silent."""
    try:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            entry = RoutingDecision(
                id=uuid.uuid4(),
                task_id=uuid.UUID(task_id),
                task_type=task_type,
                chosen_model=chosen_model,
                reasoning=_sanitize_reasoning(reasoning),
                latency_ms=latency_ms,
                success=success,
            )
            session.add(entry)
            await session.commit()
    except Exception:
        logger.debug("write_routing_decision | persistence skipped", exc_info=True)


class FallbackChain:
    """Execute a task against a concrete fallback chain with exponential backoff."""

    def __init__(
        self,
        runner: Callable[[Any, str, Optional[AsyncSession]], Awaitable[RoutingResult]],
        *,
        max_retries: int = 2,
        delay_between_retries: float = 2.0,
        sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    ) -> None:
        self._runner = runner
        self.max_retries = max_retries
        self.delay_between_retries = delay_between_retries
        self._sleep_fn = sleep_fn or asyncio.sleep

    async def execute_with_fallback(
        self,
        task: Any,
        primary_model: str,
        *,
        task_type: str,
        db: Optional[AsyncSession] = None,
    ) -> RoutingResult:
        """Try the primary model, then two fallbacks, logging every attempt."""
        chain = self._resolve_chain(task_type=task_type, primary_model=primary_model)
        last_exc: Optional[Exception] = None
        total_tokens = 0

        for attempt, model_label in enumerate(chain, start=1):
            display_name = _MODEL_LABEL_DISPLAY.get(model_label, model_label)
            try:
                result = await self._runner(task, model_label, db)
                total_tokens += result.tokens_used
                logger.info("[OK] %s succeeded at task_id=%s", display_name, getattr(task, "id", "unknown"))
                result.attempts = attempt
                result.tokens_used = total_tokens
                return result
            except Exception as exc:
                last_exc = exc
                total_tokens += int(getattr(exc, "tokens_used", 0) or 0)
                if "LiteLLM router unavailable" in str(exc):
                    logger.error("[FAIL] LiteLLM router unavailable for task_id=%s", getattr(task, "id", "unknown"))
                    raise RuntimeError("LiteLLM router unavailable") from exc
                if attempt >= len(chain):
                    logger.error("[FAIL] All models failed for task_id=%s", getattr(task, "id", "unknown"))
                    break
                next_display = _MODEL_LABEL_DISPLAY.get(chain[attempt], chain[attempt])
                logger.warning(
                    "[RETRY] %s failed (%s), trying %s...",
                    display_name,
                    self._classify_failure(exc),
                    next_display,
                )
                await self._sleep_fn(self.delay_between_retries * (2 ** (attempt - 1)))

        task_id = getattr(task, "id", "unknown")
        raise RuntimeError(f"All models failed for task_id={task_id}") from last_exc

    def _resolve_chain(self, *, task_type: str, primary_model: str) -> List[str]:
        base_chain = list(_FALLBACK_CHAINS.get(task_type, _FALLBACK_CHAINS["backend"]))
        if primary_model in base_chain:
            base_chain.remove(primary_model)
        ordered = [primary_model, *base_chain]
        return ordered[: self.max_retries + 1]

    @staticmethod
    def _classify_failure(exc: Exception) -> str:
        message = str(exc).lower()
        if "timeout" in message:
            return "timeout"
        if "rate" in message and "limit" in message:
            return "rate_limit"
        if "litellm router unavailable" in message:
            return "litellm_unavailable"
        return exc.__class__.__name__.lower()


# ---------------------------------------------------------------------------
# SmartRouter
# ---------------------------------------------------------------------------


class SmartRouter:
    """Orchestrates intelligent task parallelization with human-in-the-loop support."""

    def __init__(
        self,
        component_executor: Optional[Callable[..., Coroutine]] = None,
        user_input_fn: Optional[Callable[..., Coroutine]] = None,
        model_runner: Optional[Callable[[Any, str, Optional[AsyncSession]], Awaitable[RoutingResult]]] = None,
        sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    ) -> None:
        self._component_executor = component_executor or self._default_execute_component
        self._user_input_fn = user_input_fn or self._default_user_input
        self._settings = get_settings()
        self._model_runner = model_runner
        self._sleep_fn = sleep_fn or asyncio.sleep
        self._fallback_chain = FallbackChain(
            self._execute_task_with_model,
            max_retries=2,
            delay_between_retries=2.0,
            sleep_fn=self._sleep_fn,
        )
        self._llm_router: Any = None

    # ---------------------------------------------------------------------- #
    # Public API                                                              #
    # ---------------------------------------------------------------------- #

    def choose_model(self, task_type: str, complexity: str = "medium") -> str:
        """Choose the primary concrete model label for a task type."""
        normalized_task_type = self._normalize_task_type(task_type)
        normalized_complexity = self._normalize_complexity(complexity)

        if normalized_task_type == "backend" and normalized_complexity == "high":
            return "claude-opus"
        if normalized_task_type == "frontend" and normalized_complexity == "low":
            return "gemini-2.0-flash"
        return _TASK_TYPE_TO_MODEL.get(normalized_task_type, "claude-opus")

    async def get_model_load(self, db: Optional[AsyncSession] = None) -> Dict[str, Dict[str, int]]:
        """Return basic model load and latency stats for the last hour."""
        baseline = {
            "claude": {"requests_last_hour": 0, "avg_latency_ms": 0},
            "gemini": {"requests_last_hour": 0, "avg_latency_ms": 0},
            "codex": {"requests_last_hour": 0, "avg_latency_ms": 0},
        }
        if db is None:
            return baseline

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stmt = (
            select(
                AgentSession.model_used,
                func.count(AgentSession.id),
                func.avg(AgentSession.latency_ms),
            )
            .where(AgentSession.created_at >= cutoff)
            .group_by(AgentSession.model_used)
        )
        try:
            result = await db.execute(stmt)
            for model_used, count, avg_latency in result.all():
                model_key = model_used.value if isinstance(model_used, AgentModel) else str(model_used)
                baseline[model_key] = {
                    "requests_last_hour": int(count or 0),
                    "avg_latency_ms": int(avg_latency or 0),
                }
        except Exception as exc:
            logger.warning("get_model_load | failed to query agent_sessions: %s", exc)
        return baseline

    async def route(
        self,
        task: Any,
        *,
        db: Optional[AsyncSession] = None,
        task_type: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> RoutingResult:
        """Advanced routing entrypoint with dynamic selection, load balancing, and fallback."""
        resolved_task_type = self._resolve_task_type(task, task_type)
        resolved_complexity = self._resolve_task_complexity(task, complexity)
        model_load = await self.get_model_load(db)
        primary_model = self.choose_model(resolved_task_type, resolved_complexity)
        chosen_model = self._apply_load_balancing(
            primary_model=primary_model,
            task_type=resolved_task_type,
            complexity=resolved_complexity,
            model_load=model_load,
        )
        reasoning = self._build_routing_reasoning(
            task=task,
            task_type=resolved_task_type,
            complexity=resolved_complexity,
            chosen_model=chosen_model,
            model_load=model_load,
        )

        start = time.monotonic()
        try:
            result = await self._fallback_chain.execute_with_fallback(
                task,
                chosen_model,
                task_type=resolved_task_type,
                db=db,
            )
            total_latency_ms = int((time.monotonic() - start) * 1000)
            result.reasoning = reasoning
            result.latency_ms = total_latency_ms
            self._schedule_routing_decision_log(
                task=task,
                task_type=resolved_task_type,
                chosen_model=result.model_used,
                reasoning=reasoning,
                latency_ms=total_latency_ms,
                success=True,
            )
            logger.info(
                "task_id=%s, task_type=%s, chose=%s, latency=%dms, success=True",
                getattr(task, "id", "unknown"),
                resolved_task_type,
                result.model_used,
                total_latency_ms,
            )
            return result
        except Exception as exc:
            total_latency_ms = int((time.monotonic() - start) * 1000)
            failure_reasoning = f"{reasoning}; failure={exc}"
            self._schedule_routing_decision_log(
                task=task,
                task_type=resolved_task_type,
                chosen_model=chosen_model,
                reasoning=failure_reasoning,
                latency_ms=total_latency_ms,
                success=False,
            )
            logger.error(
                "task_id=%s, task_type=%s, chose=%s, latency=%dms, success=False, error=%s",
                getattr(task, "id", "unknown"),
                resolved_task_type,
                chosen_model,
                total_latency_ms,
                exc,
            )
            raise

    async def analyze_task(self, task_description: str) -> ExecutionPlan:
        """Detect components, infer dependencies, estimate time/cost, build plan."""
        task_id = f"smart-{int(time.time())}"
        desc_lower = task_description.lower()

        components = self._detect_components(desc_lower)
        if not components:
            components = [self._fallback_component()]

        waves = self._build_execution_waves(components)
        parallel_names = [c.name for c in components if c.type == "parallel"]
        sequential_names = [c.name for c in components if c.type == "sequential"]
        critical_name = self._find_critical_path(components)
        raw_duration = self._compute_total_duration(waves)
        total_duration = round(raw_duration * _BUFFER_FACTOR, 1)
        total_cost = sum(
            _COST_PER_COMPONENT.get(c.recommended_model, _COST_PER_COMPONENT["claude"])
            for c in components
        )
        premium_suggestion = self._build_premium_suggestion(critical_name, components)
        timeline = self._build_timeline_visualization(waves)

        plan = ExecutionPlan(
            task_id=task_id,
            estimated_total_duration_min=total_duration,
            estimated_cost_usd=round(total_cost, 4),
            components=components,
            critical_path_component=critical_name,
            parallel_components=parallel_names,
            sequential_components=sequential_names,
            premium_suggestion=premium_suggestion,
            timeline_visualization=timeline,
        )
        logger.info(
            "analyze_task | components=%d parallel=%d sequential=%d critical=%s est=%.1fmin",
            len(components),
            len(parallel_names),
            len(sequential_names),
            critical_name,
            total_duration,
        )
        return plan

    async def propose_to_user(self, plan: ExecutionPlan) -> ExecutionMode:
        """Display execution plan table and ask for execution mode selection."""
        print(self._format_plan_table(plan))
        choice = await self._user_input_fn(
            "\nEjecución: (A) Human-in-the-Loop  (B) Automatizado  → "
        )
        mode = (
            ExecutionMode.HUMAN_IN_THE_LOOP
            if choice.strip().upper() == "A"
            else ExecutionMode.AUTOMATED
        )
        logger.info("propose_to_user | mode=%s", mode.value)
        return mode

    async def execute(self, plan: ExecutionPlan, mode: ExecutionMode) -> ExecutionResult:
        """Execute the plan: asyncio.gather within waves, sequential across waves."""
        start_ts = time.monotonic()
        waves = self._build_execution_waves(plan.components)
        all_results: List[ComponentResult] = []
        failures: List[Dict] = []
        log_lines: List[str] = [
            f"[{datetime.now(timezone.utc).isoformat()}] start | mode={mode.value} "
            f"components={[c.name for c in plan.components]}"
        ]

        for wave_idx, wave in enumerate(waves):
            wave_names = [c.name for c in wave]
            log_lines.append(f"→ Wave {wave_idx + 1}/{len(waves)}: {wave_names}")

            if mode == ExecutionMode.HUMAN_IN_THE_LOOP:
                approval = await self._user_input_fn(
                    f"\n[HitL] Wave {wave_idx + 1}: ejecutar {wave_names}? (y/cancelar) → "
                )
                if approval.strip().lower() not in ("y", "yes", "s", "si"):
                    log_lines.append("  → Cancelado por usuario.")
                    break

            tasks = []
            for idx, component in enumerate(wave):
                if idx > 0:
                    await asyncio.sleep(_PARALLEL_DELAY_S)
                tasks.append(asyncio.create_task(self._component_executor(component, mode)))

            wave_results = await asyncio.gather(*tasks, return_exceptions=True)

            for component, res in zip(wave, wave_results):
                if isinstance(res, BaseException):
                    failures.append({
                        "component": component.name,
                        "error": str(res),
                        "recovery": "skipped — downstream dependencies may be affected",
                    })
                    all_results.append(ComponentResult(
                        name=component.name,
                        success=False,
                        duration_min=0.0,
                        cost_usd=0.0,
                        model_used=component.recommended_model,
                        output="",
                        error=str(res),
                    ))
                    log_lines.append(f"  ✗ {component.name}: {res}")
                else:
                    all_results.append(res)
                    if not res.success:
                        failures.append({
                            "component": res.name,
                            "error": res.error or "unknown",
                            "recovery": "component skipped",
                        })
                        log_lines.append(f"  ✗ {res.name}: {res.error}")
                    else:
                        log_lines.append(f"  ✓ {res.name} ({res.duration_min:.3f} min)")

        actual_duration = (time.monotonic() - start_ts) / 60.0
        actual_cost = sum(r.cost_usd for r in all_results)
        success = len(failures) == 0

        breakdown = self._build_parallelization_breakdown(waves, plan, all_results)
        suggestions = self._generate_suggestions(plan, all_results, failures)
        log_lines.append(
            f"[{datetime.now(timezone.utc).isoformat()}] end | success={success} "
            f"duration={actual_duration:.3f}min cost=${actual_cost:.4f}"
        )

        return ExecutionResult(
            success=success,
            actual_duration_min=round(actual_duration, 3),
            actual_cost_usd=round(actual_cost, 4),
            failures=failures,
            parallelization_breakdown=breakdown,
            execution_log="\n".join(log_lines),
            suggestions=suggestions,
        )

    async def generate_report(self, result: ExecutionResult) -> str:
        """Structured report: Failures → Cost+Time → Parallelization → Suggestions."""
        bd = result.parallelization_breakdown
        lines: List[str] = [
            "=" * 62,
            "  SMART ROUTER — EXECUTION REPORT",
            "=" * 62,
            "",
            "## 1. FALLOS",
        ]

        if not result.failures:
            lines.append("   ✓ Sin fallos — todos los componentes completados.")
        else:
            for f in result.failures:
                lines.append(f"   ✗ {f['component']}: {f['error']}")
                lines.append(f"     → Recuperación: {f.get('recovery', 'N/A')}")
        lines.append("")

        lines += [
            "## 2. COSTO + TIEMPO",
            f"   Tiempo real     : {result.actual_duration_min:.3f} min",
            f"   Tiempo estimado : {bd.get('estimated_total_min', '?')} min",
            f"   Costo real      : ${result.actual_cost_usd:.4f}",
            f"   Costo estimado  : ${bd.get('estimated_cost_usd', '?'):.4f}",
            f"   Modelos usados  : {bd.get('models_used', [])}",
            "",
            "## 3. PARALELIZACIÓN",
            f"   Paralelos        : {bd.get('parallel_components', [])}",
            f"   Secuenciales     : {bd.get('sequential_components', [])}",
            f"   Ganancia vs serie: {bd.get('time_saved_min', 0.0):.2f} min",
            "",
            "## 4. SUGERENCIAS PARA PRÓXIMA VEZ",
        ]

        if result.suggestions:
            for s in result.suggestions:
                lines.append(f"   • {s}")
        else:
            lines.append("   • Sin sugerencias adicionales.")

        lines += ["", "=" * 62]
        return "\n".join(lines)

    # ---------------------------------------------------------------------- #
    # Detection & planning helpers                                            #
    # ---------------------------------------------------------------------- #

    def _detect_components(self, desc_lower: str) -> List[ComponentAnalysis]:
        detected_names: set[str] = set()
        found: List[ComponentAnalysis] = []

        for name, meta in _COMPONENT_PATTERNS.items():
            if any(kw in desc_lower for kw in meta["keywords"]):
                detected_names.add(name)

        for name in detected_names:
            meta = _COMPONENT_PATTERNS[name]
            pruned_deps = [d for d in meta["depends_on"] if d in detected_names]
            found.append(ComponentAnalysis(
                name=name,
                type="sequential" if pruned_deps else "parallel",
                depends_on=pruned_deps,
                estimated_duration_min=self._estimate_duration(name, desc_lower, meta["base_duration_min"]),
                recommended_model=meta["model"],
            ))

        return found

    def _fallback_component(self) -> ComponentAnalysis:
        return ComponentAnalysis(
            name="Task",
            type="parallel",
            depends_on=[],
            estimated_duration_min=7.0,
            recommended_model="claude",
        )

    def _estimate_duration(self, _name: str, desc_lower: str, base: float) -> float:
        if any(w in desc_lower for w in _COMPLEXITY_KEYWORDS_HIGH):
            mult = 1.4
        elif any(w in desc_lower for w in _COMPLEXITY_KEYWORDS_LOW):
            mult = 0.7
        else:
            mult = 1.0
        extra = sum(int(n) for n in re.findall(r"\b(\d+)\s*endpoint", desc_lower)) * 0.05
        return round(base * (mult + extra), 1)

    def _build_execution_waves(
        self, components: List[ComponentAnalysis]
    ) -> List[List[ComponentAnalysis]]:
        remaining = {c.name: c for c in components}
        completed: set[str] = set()
        waves: List[List[ComponentAnalysis]] = []

        while remaining:
            wave = [c for c in remaining.values() if all(d in completed for d in c.depends_on)]
            if not wave:
                # Circular dependency guard — force all remaining into one wave
                logger.warning("smart_router | unresolvable dependencies, forcing single wave")
                wave = list(remaining.values())
            for c in wave:
                completed.add(c.name)
                del remaining[c.name]
            waves.append(wave)

        return waves

    def _find_critical_path(self, components: List[ComponentAnalysis]) -> str:
        return max(components, key=lambda c: c.estimated_duration_min).name

    def _compute_total_duration(self, waves: List[List[ComponentAnalysis]]) -> float:
        return sum(max(c.estimated_duration_min for c in wave) for wave in waves)

    def _build_premium_suggestion(
        self, critical_name: str, components: List[ComponentAnalysis]
    ) -> Optional[Dict]:
        critical = next((c for c in components if c.name == critical_name), None)
        if not critical or critical.estimated_duration_min < _PREMIUM_THRESHOLD_MIN:
            return None
        premium = _PREMIUM_MODELS.get(critical.recommended_model, "claude-opus-4-7")
        time_saved = round(critical.estimated_duration_min * (1 - 1 / _PREMIUM_SPEEDUP), 1)
        return {
            "component": critical.name,
            "current_model": critical.recommended_model,
            "suggested_model": premium,
            "estimated_time_saved_min": time_saved,
            "reason": (
                f"{critical.name} es el camino crítico ({critical.estimated_duration_min} min). "
                f"{premium} es ~{_PREMIUM_SPEEDUP}× más rápido en tareas complejas."
            ),
        }

    def _build_timeline_visualization(
        self, waves: List[List[ComponentAnalysis]]
    ) -> str:
        all_comps = [c for wave in waves for c in wave]
        if not all_comps:
            return "Timeline: (empty)"
        max_dur = max(c.estimated_duration_min for c in all_comps)
        scale = 24.0 / max_dur
        lines = ["Timeline (estimated):"]
        offset = 0.0
        for wave in waves:
            for comp in wave:
                pad = int(offset * scale)
                bar = max(1, int(comp.estimated_duration_min * scale))
                lines.append(f"  {'':>{pad}}{'█' * bar} {comp.name} ({comp.estimated_duration_min:.1f}m)")
            offset += max(c.estimated_duration_min for c in wave)
        return "\n".join(lines)

    def _format_plan_table(self, plan: ExecutionPlan) -> str:
        lines = [
            "",
            "╔══ SMART ROUTER — EXECUTION PLAN ══════════════════════════╗",
            f"║  Task     : {plan.task_id}",
            f"║  Duration : {plan.estimated_total_duration_min:.1f} min (incl. 20% buffer)",
            f"║  Cost     : ${plan.estimated_cost_usd:.4f}",
            f"║  Critical : {plan.critical_path_component}",
            "╠════════════════════════════════════════════════════════════╣",
            f"  {'Component':<20} {'Model':<10} {'Min':<8} {'Type':<12}",
            "  " + "─" * 52,
        ]
        for c in plan.components:
            lines.append(
                f"  {c.name:<20} {c.recommended_model:<10} {c.estimated_duration_min:<8.1f} {c.type:<12}"
            )
        lines += [
            "  " + "─" * 52,
            f"  {'TOTAL (parallelized)':<20} {'—':<10} {plan.estimated_total_duration_min:<8.1f}",
        ]
        if plan.premium_suggestion:
            ps = plan.premium_suggestion
            lines.append(
                f"\n  ⚡ Sugerencia premium: {ps['suggested_model']} para {ps['component']}"
                f" → ahorra ~{ps['estimated_time_saved_min']} min"
            )
        lines += ["╚════════════════════════════════════════════════════════════╝", plan.timeline_visualization]
        return "\n".join(lines)

    def _build_parallelization_breakdown(
        self,
        waves: List[List[ComponentAnalysis]],
        plan: ExecutionPlan,
        results: List[ComponentResult],
    ) -> Dict:
        result_map = {r.name: r for r in results}
        parallel_comps = [c.name for c in waves[0]] if waves else []
        sequential_comps = [c.name for wave in waves[1:] for c in wave]
        models_used = sorted({r.model_used for r in results})

        serial_time = sum(r.duration_min for r in results)
        parallel_time = sum(
            max((result_map[c.name].duration_min for c in wave if c.name in result_map), default=0.0)
            for wave in waves
        )
        est_total = sum(
            max(c.estimated_duration_min for c in wave) for wave in waves
        )

        return {
            "parallel_components": parallel_comps,
            "sequential_components": sequential_comps,
            "models_used": models_used,
            "time_saved_min": round(max(0.0, serial_time - parallel_time), 3),
            "estimated_total_min": round(est_total * _BUFFER_FACTOR, 1),
            "estimated_cost_usd": plan.estimated_cost_usd,
        }

    def _generate_suggestions(
        self,
        plan: ExecutionPlan,
        results: List[ComponentResult],
        failures: List[Dict],
    ) -> List[str]:
        suggestions: List[str] = []

        successful = [r for r in results if r.success]
        if successful:
            slowest = max(successful, key=lambda r: r.duration_min)
            if slowest.duration_min > 6.0 / 60:  # > 6s wall-clock → likely slow in prod
                premium = _PREMIUM_MODELS.get(slowest.model_used, "claude-opus-4-7")
                saved = round(slowest.duration_min * (1 - 1 / _PREMIUM_SPEEDUP), 3)
                suggestions.append(
                    f"Próxima vez usa {premium} para {slowest.name} (podría ahorrar ~{saved} min)"
                )

        for f in failures:
            comp = next((c for c in plan.components if c.name == f["component"]), None)
            if comp:
                premium = _PREMIUM_MODELS.get(comp.recommended_model, "claude-opus-4-7")
                suggestions.append(f"{comp.name} falló — considera {premium} para mayor robustez")

        if len(plan.sequential_components) > len(plan.parallel_components):
            suggestions.append(
                "Muchos componentes secuenciales — descompón la tarea para maximizar paralelización"
            )

        return suggestions

    # ---------------------------------------------------------------------- #
    # Advanced routing helpers                                                #
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _normalize_task_type(task_type: str) -> str:
        normalized = (task_type or "backend").strip().lower()
        return normalized if normalized in _TASK_TYPE_TO_MODEL else "backend"

    @staticmethod
    def _normalize_complexity(complexity: str) -> str:
        normalized = (complexity or "medium").strip().lower()
        return normalized if normalized in {"low", "medium", "high"} else "medium"

    def _resolve_task_type(self, task: Any, explicit_task_type: Optional[str]) -> str:
        if explicit_task_type:
            return self._normalize_task_type(explicit_task_type)

        task_type = getattr(task, "task_type", None)
        if isinstance(task_type, str) and task_type.strip():
            return self._normalize_task_type(task_type)

        haystack = " ".join(
            str(value or "")
            for value in (
                getattr(task, "name", ""),
                getattr(task, "prompt_sent", ""),
                getattr(task, "description", ""),
            )
        ).lower()

        if any(keyword in haystack for keyword in ("react", "frontend", "ui", "component", "dashboard")):
            return "frontend"
        if any(keyword in haystack for keyword in ("pytest", "test", "coverage", "qa")):
            return "testing"
        if any(keyword in haystack for keyword in ("security", "auth", "jwt", "owasp")):
            return "security"
        if any(keyword in haystack for keyword in ("integration", "slack", "jira", "github", "webhook")):
            return "integration"
        return "backend"

    def _resolve_task_complexity(self, task: Any, explicit_complexity: Optional[str]) -> str:
        if explicit_complexity:
            return self._normalize_complexity(explicit_complexity)

        task_complexity = getattr(task, "complexity", None)
        if isinstance(task_complexity, str) and task_complexity.strip():
            return self._normalize_complexity(task_complexity)

        haystack = " ".join(
            str(value or "")
            for value in (
                getattr(task, "name", ""),
                getattr(task, "prompt_sent", ""),
                getattr(task, "description", ""),
            )
        ).lower()
        if any(keyword in haystack for keyword in _COMPLEXITY_KEYWORDS_HIGH):
            return "high"
        if any(keyword in haystack for keyword in _COMPLEXITY_KEYWORDS_LOW):
            return "low"
        return "medium"

    def _apply_load_balancing(
        self,
        *,
        primary_model: str,
        task_type: str,
        complexity: str,
        model_load: Dict[str, Dict[str, int]],
    ) -> str:
        if task_type in {"backend", "integration"} and complexity == "high":
            return primary_model

        claude_load = model_load.get("claude", {}).get("requests_last_hour", 0)
        gemini_load = model_load.get("gemini", {}).get("requests_last_hour", 0)

        if primary_model == "claude-opus" and claude_load >= 100 and task_type not in {"security"}:
            return "gemini-2.0-flash"
        if gemini_load < 50 and task_type in {"frontend"}:
            return "gemini-2.0-flash"
        return primary_model

    def _build_routing_reasoning(
        self,
        *,
        task: Any,
        task_type: str,
        complexity: str,
        chosen_model: str,
        model_load: Dict[str, Dict[str, int]],
    ) -> str:
        task_id = getattr(task, "id", "unknown")
        claude_load = model_load.get("claude", {}).get("requests_last_hour", 0)
        gemini_load = model_load.get("gemini", {}).get("requests_last_hour", 0)
        codex_load = model_load.get("codex", {}).get("requests_last_hour", 0)
        load_factor = f"claude={claude_load}/h, gemini={gemini_load}/h, codex={codex_load}/h"
        rationale = {
            "frontend": "frontend/UI work prefers Gemini for speed",
            "backend": "backend reasoning prefers Claude",
            "testing": "testing and QA prefers Codex discipline",
            "integration": "integration/API work prefers Claude depth",
            "security": "security review prefers Codex audit focus",
        }.get(task_type, "defaulted to backend routing policy")
        if chosen_model == "gemini-2.0-flash" and task_type != "frontend":
            rationale = f"{rationale}; load balancing shifted traffic away from Claude"
        return (
            f"task_id={task_id}, task_type={task_type}, complexity={complexity}, "
            f"chose={chosen_model} ({rationale}, {load_factor})"
        )

    def _schedule_routing_decision_log(
        self,
        *,
        task: Any,
        task_type: str,
        chosen_model: str,
        reasoning: str,
        latency_ms: int,
        success: bool,
    ) -> None:
        task_id = getattr(task, "id", None)
        if task_id is None:
            return
        asyncio.create_task(
            write_routing_decision(
                task_id=str(task_id),
                task_type=task_type,
                chosen_model=chosen_model,
                reasoning=reasoning,
                latency_ms=latency_ms,
                success=success,
            )
        )

    async def _execute_task_with_model(
        self,
        task: Any,
        model_label: str,
        db: Optional[AsyncSession],
    ) -> RoutingResult:
        if self._model_runner is not None:
            return await self._model_runner(task, model_label, db)

        router = self._get_model_router()
        provider_model = self._resolve_provider_model(model_label)
        model_assigned = _MODEL_LABEL_TO_AGENT[model_label]
        prompt = self._build_prompt_for_task(task)
        system_prompt = f"Task type: {self._resolve_task_type(task, None)}"

        try:
            route_result = await router._call_model(
                task_id=getattr(task, "id"),
                model=provider_model,
                model_assigned=model_assigned,
                prompt=prompt,
                system_prompt=system_prompt,
                attempt=1,
                temperature=0.2,
                max_tokens=4096,
                db=db,
            )
        except Exception as exc:
            error_type = FallbackChain._classify_failure(exc)
            await router._log_failed_session(
                task_id=getattr(task, "id"),
                model_assigned=model_assigned,
                model_version=provider_model,
                error_type=error_type,
                error_message=str(exc),
                db=db,
            )
            raise RuntimeError(f"{provider_model} failed: {exc}") from exc

        return RoutingResult(
            content=route_result.content,
            model_used=model_label,
            provider_model=provider_model,
            latency_ms=route_result.latency_ms,
            tokens_used=route_result.tokens_total,
            attempts=1,
            reasoning="",
            success=True,
        )

    def _get_model_router(self) -> Any:
        if self._llm_router is None:
            try:
                from app.agents.litellm_router import get_router

                self._llm_router = get_router()
            except Exception as exc:
                raise RuntimeError("LiteLLM router unavailable") from exc
        return self._llm_router

    def _resolve_provider_model(self, model_label: str) -> str:
        provider_models = {
            "claude-opus": self._settings.claude_model,
            "gemini-2.0-flash": "gemini/gemini-2.0-flash",
            "gpt-4o": "openai/gpt-4o",
        }
        return provider_models[model_label]

    @staticmethod
    def _build_prompt_for_task(task: Any) -> str:
        for attr in ("prompt_sent", "description", "name"):
            value = getattr(task, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise RuntimeError("LiteLLM task prompt is empty")

    # ---------------------------------------------------------------------- #
    # Default implementations (replaceable in tests)                          #
    # ---------------------------------------------------------------------- #

    async def _default_execute_component(
        self, component: ComponentAnalysis, mode: ExecutionMode
    ) -> ComponentResult:
        """Simulate component execution. Replace with real ModelRouter call in production."""
        start = time.monotonic()
        sim_s = min(component.estimated_duration_min * 0.1, 1.0)
        await asyncio.sleep(sim_s)
        elapsed_min = (time.monotonic() - start) / 60.0
        cost = _COST_PER_COMPONENT.get(component.recommended_model, _COST_PER_COMPONENT["claude"])
        return ComponentResult(
            name=component.name,
            success=True,
            duration_min=round(elapsed_min, 4),
            cost_usd=round(cost, 4),
            model_used=component.recommended_model,
            output=f"[sim] {component.name} completed by {component.recommended_model}",
        )

    @staticmethod
    async def _default_user_input(prompt: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)
