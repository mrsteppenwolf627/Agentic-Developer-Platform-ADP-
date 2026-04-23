"""Compatibility wrapper for SmartRouter advanced routing.

FASE 5 references `app.integrations.smart_router`, while the original router
implementation lives in `app.agents.smart_router`. Re-export the advanced
routing surface from the canonical module to avoid breaking existing imports.
"""
from app.agents.smart_router import (
    ComponentAnalysis,
    ComponentResult,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    FallbackChain,
    RoutingResult,
    SmartRouter,
    write_routing_decision,
)

__all__ = [
    "ComponentAnalysis",
    "ComponentResult",
    "ExecutionMode",
    "ExecutionPlan",
    "ExecutionResult",
    "FallbackChain",
    "RoutingResult",
    "SmartRouter",
    "write_routing_decision",
]
