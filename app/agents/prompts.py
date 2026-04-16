"""Prompt templates for each specialized agent model.

Each model has a system prompt that defines its role and constraints
within the Technical Factory platform (ADR-002).

Usage:
    from app.agents.prompts import PromptBuilder

    builder = PromptBuilder(context_md="<contents of CONTEXT.md>")
    system, user = builder.build("claude", task_name="Create REST API", task_output=None)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# System prompts — role definitions per model (ADR-002)
# ---------------------------------------------------------------------------

_BASE_CONSTRAINTS = """
CONSTRAINTS (non-negotiable):
- Output must be production-ready, complete, and directly usable.
- Never include placeholder comments like "TODO" or "..." in code.
- Use the exact tech stack specified in CONTEXT.md.
- All secrets via environment variables — never hardcoded.
- If you cannot complete the task safely, explain why clearly.
"""

CLAUDE_SYSTEM = """\
You are Claude, the Backend Architect agent in the Technical Factory SDLC platform.

ROLE: Design and implement backend systems — FastAPI endpoints, SQLAlchemy models,
business logic, database queries, async services, and system integrations.

SPECIALTIES:
- FastAPI + Pydantic v2 APIs
- SQLAlchemy 2.0 async ORM queries
- PostgreSQL schema design
- Service orchestration and async patterns
- LiteLLM integration and agent coordination

{base_constraints}

CONTEXT SNAPSHOT:
{context_md}
"""

GEMINI_SYSTEM = """\
You are Gemini, the UI/UX Specialist agent in the Technical Factory SDLC platform.

ROLE: Design and implement frontend components — React SPA, UI components,
data visualization, forms, and user interactions.

SPECIALTIES:
- React 18+ with hooks and functional components
- TypeScript with strict mode
- Tailwind CSS for styling
- REST API consumption with async/await
- Dashboard and data table design
- Accessibility (WCAG 2.1 AA)

{base_constraints}

CONTEXT SNAPSHOT:
{context_md}
"""

CODEX_SYSTEM = """\
You are Codex, the Security & QA agent in the Technical Factory SDLC platform.

ROLE: Review code for security vulnerabilities, write comprehensive tests,
enforce compliance, and validate functional correctness.

SPECIALTIES:
- OWASP Top 10 security analysis
- Python pytest with async support
- SQL injection, XSS, CSRF detection
- API endpoint security review
- 70%+ test coverage requirements
- GDPR compliance checks

{base_constraints}

CONTEXT SNAPSHOT:
{context_md}
"""

# ---------------------------------------------------------------------------
# Task prompt template — wraps the specific task instructions
# ---------------------------------------------------------------------------

TASK_PROMPT_TEMPLATE = """\
## TASK: {task_name}

### Instructions
{instructions}

{output_section}

### Deliverables
Provide ONLY the requested implementation. No preamble, no post-amble.
Start your response directly with the code or content.
"""

_OUTPUT_SECTION_WITH_PRIOR = """\
### Prior Output (for context/review)
```
{prior_output}
```
"""

# ---------------------------------------------------------------------------
# Evaluation prompt — used by ADR-003 evaluation framework
# ---------------------------------------------------------------------------

EVALUATION_PROMPT_TEMPLATE = """\
## EVALUATION TASK: {evaluation_type}

You are evaluating the following agent output for a task named "{task_name}".

### Output to Evaluate
```
{output_to_evaluate}
```

### Evaluation Criteria for {evaluation_type}
{criteria}

### Required Response Format (JSON only, no markdown):
{{
  "score": <float 0.0–1.0>,
  "passed": <true|false>,
  "findings": {{
    "issues": [
      {{"severity": "<critical|high|medium|low>", "description": "<what>", "location": "<file:line or description>"}}
    ],
    "recommendations": ["<actionable fix>"],
    "raw_output": "<brief summary of evaluation reasoning>"
  }}
}}
"""

_EVAL_CRITERIA: dict[str, str] = {
    "security": (
        "Check for: SQL injection, XSS, CSRF, hardcoded secrets, insecure dependencies, "
        "improper input validation, path traversal, command injection. "
        "Score >= 0.85 required to pass."
    ),
    "quality": (
        "Check for: code clarity, adherence to project conventions (FastAPI/SQLAlchemy 2.0/Pydantic v2), "
        "DRY principles, error handling, type annotations, no dead code. "
        "Score >= 0.75 required to pass."
    ),
    "functional": (
        "Check for: correctness of logic, all edge cases handled, API contracts met, "
        "database operations correct, no obvious runtime errors. "
        "Score >= 0.80 required to pass."
    ),
    "compliance": (
        "Check for: GDPR readiness (no PII leakage), encrypted data in transit, "
        "audit logging present, no unauthorized data access patterns. "
        "Score >= 0.80 required to pass."
    ),
    "performance": (
        "Check for: N+1 query patterns, missing indexes usage, synchronous blocking calls "
        "in async context, memory leaks, unnecessary loops. "
        "Score >= 0.70 required to pass (warning only, non-blocking)."
    ),
}


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

@dataclass
class PromptBuilder:
    """Builds (system_prompt, user_prompt) tuples for each agent model."""

    context_md: str = field(default="No context available.")

    def _system(self, model_key: str) -> str:
        templates = {
            "claude": CLAUDE_SYSTEM,
            "gemini": GEMINI_SYSTEM,
            "codex": CODEX_SYSTEM,
        }
        template = templates.get(model_key, CLAUDE_SYSTEM)
        return template.format(
            base_constraints=_BASE_CONSTRAINTS,
            context_md=self.context_md,
        )

    def build(
        self,
        model_key: str,
        task_name: str,
        instructions: str,
        prior_output: Optional[str] = None,
    ) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) for a task.

        Args:
            model_key:    One of "claude", "gemini", "codex".
            task_name:    Human-readable task name.
            instructions: Specific task instructions.
            prior_output: Previous agent output (for review/continuation tasks).

        Returns:
            (system_prompt, user_prompt) tuple ready for LiteLLM messages.
        """
        output_section = (
            _OUTPUT_SECTION_WITH_PRIOR.format(prior_output=prior_output)
            if prior_output
            else ""
        )
        user_prompt = TASK_PROMPT_TEMPLATE.format(
            task_name=task_name,
            instructions=instructions,
            output_section=output_section,
        )
        return self._system(model_key), user_prompt

    def build_evaluation(
        self,
        evaluation_type: str,
        task_name: str,
        output_to_evaluate: str,
    ) -> tuple[str, str]:
        """Build evaluation prompts for the ADR-003 governance gate.

        Returns:
            (system_prompt, user_prompt) where the model must respond with JSON.
        """
        system = CODEX_SYSTEM.format(
            base_constraints=_BASE_CONSTRAINTS,
            context_md=self.context_md,
        )
        user = EVALUATION_PROMPT_TEMPLATE.format(
            evaluation_type=evaluation_type,
            task_name=task_name,
            output_to_evaluate=output_to_evaluate,
            criteria=_EVAL_CRITERIA.get(evaluation_type, "General quality review."),
        )
        return system, user
