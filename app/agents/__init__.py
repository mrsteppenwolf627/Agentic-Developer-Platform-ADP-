"""agents package — LiteLLM router, prompt templates, and SmartRouter."""

from app.agents.litellm_router import ModelRouter, RouteResult, RouterError, ModelRouterError, get_router
from app.agents.prompts import PromptBuilder
from app.agents.smart_router import (
    SmartRouter,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ComponentAnalysis,
    ComponentResult,
)

__all__ = [
    "ModelRouter",
    "RouteResult",
    "RouterError",
    "ModelRouterError",
    "get_router",
    "PromptBuilder",
    "SmartRouter",
    "ExecutionMode",
    "ExecutionPlan",
    "ExecutionResult",
    "ComponentAnalysis",
    "ComponentResult",
]
