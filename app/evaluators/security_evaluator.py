"""Static security checks for generated code outputs."""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Finding(BaseModel):
    """Normalized issue produced by a single evaluation rule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pillar: str = Field(..., min_length=1)
    severity: str = Field(..., pattern="^(CRITICAL|HIGH|MEDIUM)$")
    category: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    line: Optional[int] = Field(None, ge=1)
    recommendation: str = Field(..., min_length=1)

    @field_validator("pillar")
    @classmethod
    def normalize_pillar(cls, value: str) -> str:
        return value.upper()


class SecurityEvaluator:
    """Heuristic SAST-style scanner for common high-risk vulnerabilities."""

    _SQLI_PATTERNS = [
        (
            re.compile(r"(SELECT|INSERT|UPDATE|DELETE).*(\+|%|\{.+\}|format\()", re.IGNORECASE),
            "HIGH",
            "SQL_INJECTION",
            "Possible SQL injection via string-built query.",
            "Use parameterized queries or ORM query builders instead of string interpolation.",
        ),
        (
            re.compile(r"cursor\.execute\s*\(\s*f?[\"'].*\{", re.IGNORECASE),
            "HIGH",
            "SQL_INJECTION",
            "Database execute call appears to interpolate untrusted input directly.",
            "Bind values separately when calling execute().",
        ),
    ]
    _XSS_PATTERNS = [
        (
            re.compile(r"dangerouslySetInnerHTML|innerHTML\s*=", re.IGNORECASE),
            "HIGH",
            "XSS",
            "Potential DOM XSS sink detected.",
            "Sanitize user-controlled HTML or render escaped content only.",
        ),
        (
            re.compile(r"mark_safe\s*\(|SafeString\s*\(", re.IGNORECASE),
            "MEDIUM",
            "XSS",
            "Unsafe explicit HTML trust boundary detected.",
            "Avoid bypassing escaping unless content is sanitized.",
        ),
    ]
    _SECRET_PATTERNS = [
        (
            re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\n]{8,}[\"']", re.IGNORECASE),
            "CRITICAL",
            "HARDCODED_SECRET",
            "Possible hardcoded credential or API key detected.",
            "Load secrets from environment variables or a dedicated secret manager.",
        ),
        (
            re.compile(r"sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{20,}", re.IGNORECASE),
            "CRITICAL",
            "HARDCODED_SECRET",
            "Credential-like token detected in source code.",
            "Remove the secret from source control and rotate it immediately.",
        ),
    ]
    _CRYPTO_PATTERNS = [
        (
            re.compile(r"\b(md5|sha1)\s*\(", re.IGNORECASE),
            "HIGH",
            "UNSAFE_CRYPTO",
            "Weak cryptographic hash usage detected.",
            "Use a modern primitive such as SHA-256 or a password hashing algorithm like bcrypt/Argon2.",
        ),
        (
            re.compile(r"(DES|ECB|ARC4|random\.random\()", re.IGNORECASE),
            "HIGH",
            "UNSAFE_CRYPTO",
            "Insecure cryptographic primitive or weak randomness detected.",
            "Use authenticated encryption and the secrets module or a vetted crypto library.",
        ),
    ]

    def evaluate(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(output_code.splitlines(), start=1):
            findings.extend(self._scan_patterns(line, index, self._SQLI_PATTERNS))
            findings.extend(self._scan_patterns(line, index, self._XSS_PATTERNS))
            findings.extend(self._scan_patterns(line, index, self._SECRET_PATTERNS))
            findings.extend(self._scan_patterns(line, index, self._CRYPTO_PATTERNS))
        return findings

    @staticmethod
    def _scan_patterns(
        line: str,
        line_number: int,
        rules: list[tuple[re.Pattern[str], str, str, str, str]],
    ) -> List[Finding]:
        matches: List[Finding] = []
        for pattern, severity, category, description, recommendation in rules:
            if pattern.search(line):
                matches.append(
                    Finding(
                        pillar="SECURITY",
                        severity=severity,
                        category=category,
                        description=description,
                        line=line_number,
                        recommendation=recommendation,
                    )
                )
        return matches
