#!/usr/bin/env python3
"""
Interactive .env updater with friendly questionnaire for ADP credentials.
"""

import os
import sys
import re
import io
from pathlib import Path
from typing import Dict, Optional, Tuple

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_env() -> Dict[str, str]:
    """Load existing .env variables."""
    env_path = Path(".env")
    env_vars = {}

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()

    return env_vars

def print_box(title: str, content: str):
    """Print a formatted box with content."""
    lines = content.split('\n')
    max_width = max(len(line) for line in lines) + 2

    print("┌" + "─" * max_width + "┐")
    print(f"│ {title}" + " " * (max_width - len(title) - 1) + "│")
    print("├" + "─" * max_width + "┤")
    for line in lines:
        print(f"│ {line}" + " " * (max_width - len(line) - 1) + "│")
    print("└" + "─" * max_width + "┘")

def validate_slack_token(value: str) -> Tuple[bool, str]:
    """Validate Slack bot token."""
    if not value.startswith("xoxb-"):
        return False, "Token Slack debe empezar con 'xoxb-'"
    if len(value) < 20:
        return False, "Token Slack parece incompleto"
    return True, "✓"

def validate_jira_url(value: str) -> Tuple[bool, str]:
    """Validate Jira URL."""
    if "atlassian.net" not in value:
        return False, "URL debe contener 'atlassian.net'"
    if not value.startswith("http"):
        return False, "URL debe empezar con 'http' o 'https'"
    return True, "✓"

def validate_jira_email(value: str) -> Tuple[bool, str]:
    """Validate email format."""
    if "@" not in value:
        return False, "Email debe contener '@'"
    if "." not in value.split("@")[1]:
        return False, "Email parece inválido"
    return True, "✓"

def validate_jira_token(value: str) -> Tuple[bool, str]:
    """Validate Jira API token."""
    if len(value) < 50:
        return False, "Token Jira debe tener al menos 50 caracteres"
    return True, "✓"

def validate_github_token(value: str) -> Tuple[bool, str]:
    """Validate GitHub personal access token."""
    if not value.startswith("ghp_"):
        return False, "Token GitHub debe empezar con 'ghp_'"
    if len(value) < 20:
        return False, "Token GitHub parece incompleto"
    return True, "✓"

def ask_credential(question_num: int, label: str, hint: str, validator, current_value: Optional[str] = None) -> str:
    """Ask for a single credential with validation."""
    max_attempts = 3
    attempt = 0

    while attempt < max_attempts:
        print(f"\n🔐 Pregunta {question_num}/5: {label}")
        print_box(hint, f"Pégalo aquí:")

        value = input("→ ").strip()

        if not value:
            if current_value:
                use_current = input("\n¿Usar valor actual? (s/n): ").strip().lower()
                if use_current == 's':
                    return current_value
            print("❌ El valor no puede estar vacío. Intenta de nuevo.\n")
            attempt += 1
            continue

        # Validate
        is_valid, message = validator(value)
        if not is_valid:
            print(f"❌ {message}")
            attempt += 1
            if attempt < max_attempts:
                print(f"   Intentos restantes: {max_attempts - attempt}\n")
            continue

        print(f"✅ {label} guardado correctamente\n")
        return value

    print(f"\n❌ Demasiados intentos fallidos. Abortando.")
    sys.exit(1)

def main():
    """Main interactive flow."""
    print("\n" + "=" * 50)
    print("🔐 ACTUALIZAR .env - FASE 2 INTEGRATIONS")
    print("=" * 50)

    # Load existing env
    existing_env = load_env()

    # Define questions
    questions = [
        {
            "num": 1,
            "label": "Slack Bot Token",
            "hint": "Este token empieza con 'xoxb-'\nLo sacaste de https://api.slack.com",
            "key": "SLACK_BOT_TOKEN",
            "validator": validate_slack_token,
        },
        {
            "num": 2,
            "label": "Jira URL",
            "hint": "Formato: https://nombre.atlassian.net\nSin barra al final",
            "key": "JIRA_URL",
            "validator": validate_jira_url,
        },
        {
            "num": 3,
            "label": "Jira Email",
            "hint": "Tu email asociado a Jira\nFormato: user@example.com",
            "key": "JIRA_EMAIL",
            "validator": validate_jira_email,
        },
        {
            "num": 4,
            "label": "Jira API Token",
            "hint": "Generado en https://id.atlassian.com/manage/api-tokens\nTiene más de 50 caracteres",
            "key": "JIRA_TOKEN",
            "validator": validate_jira_token,
        },
        {
            "num": 5,
            "label": "GitHub Token (PAT)",
            "hint": "Personal Access Token desde https://github.com/settings/tokens\nEmpieza con 'ghp_'",
            "key": "GITHUB_TOKEN",
            "validator": validate_github_token,
        },
    ]

    new_values = {}

    for q in questions:
        current = existing_env.get(q["key"])
        value = ask_credential(
            q["num"],
            q["label"],
            q["hint"],
            q["validator"],
            current_value=current
        )
        new_values[q["key"]] = value

    # Show summary
    print("\n" + "=" * 50)
    print("✅ Resumen de Configuración")
    print("=" * 50 + "\n")

    for key, value in new_values.items():
        masked = value[:15] + "..." if len(value) > 15 else value
        print(f"  • {key}: {masked}")

    print("\n")
    confirm = input("¿Guardar estos valores en .env? (s/n): ").strip().lower()

    if confirm != 's':
        print("\n❌ Cancelado. No se realizaron cambios.\n")
        sys.exit(0)

    # Update .env preserving existing variables
    final_env = existing_env.copy()
    final_env.update(new_values)

    # Write to file
    env_path = Path(".env")
    with open(env_path, 'w') as f:
        for key in sorted(final_env.keys()):
            f.write(f"{key}={final_env[key]}\n")

    print(f"\n✨ Éxito! {env_path} actualizado correctamente")
    print(f"   {len(new_values)} variables de configuración guardadas.\n")

if __name__ == "__main__":
    main()
