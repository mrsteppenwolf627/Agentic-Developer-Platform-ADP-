"""Dry-run health check for all configured LLM models.

Run from project root:
    python scripts/check_models.py

Exits with code 0 if all models respond, 1 if any fail.
Does NOT require a running database.
"""
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.litellm_router import get_router
from app.config import get_settings


async def main() -> int:
    settings = get_settings()

    print("=" * 60)
    print("ADP Model Health Check")
    print(f"  claude : {settings.claude_model}")
    print(f"  gemini : {settings.gemini_model}")
    print(f"  codex  : {settings.codex_model}")
    print("=" * 60)

    keys_present = {
        "ANTHROPIC_API_KEY": bool(settings.anthropic_api_key),
        "GOOGLE_API_KEY": bool(settings.google_api_key),
        "OPENAI_API_KEY": bool(settings.openai_api_key),
    }
    for k, present in keys_present.items():
        status = "✓ set" if present else "✗ MISSING"
        print(f"  {k:<25} {status}")
    print()

    if not any(keys_present.values()):
        print("ERROR: No API keys configured. Fill in .env and retry.")
        return 1

    router = get_router()
    results = await router.health_check()

    all_ok = True
    for model_key, info in results.items():
        icon = "✓" if info["status"] == "ok" else "✗"
        latency = f"{info['latency_ms']}ms" if info["latency_ms"] else "—"
        error = f"  ERROR: {info['error']}" if info["error"] else ""
        print(f"  {icon} {model_key:<8} ({info['model']:<35}) {latency}{error}")
        if info["status"] != "ok":
            all_ok = False

    print()
    if all_ok:
        print("All models healthy. Router ready.")
    else:
        print("One or more models failed. Check API keys and quotas.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
