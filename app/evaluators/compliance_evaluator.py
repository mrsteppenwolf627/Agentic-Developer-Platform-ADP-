"""Compliance checks for governance policies."""
from __future__ import annotations

import re
from typing import List

from app.evaluators.security_evaluator import Finding


class ComplianceEvaluator:
    """Checks GDPR, ISO 27001 and custom internal policies."""

    _PERSONAL_DATA_PATTERN = re.compile(
        r"\b(email|phone|ssn|passport|dni|address|personal_data|pii)\b",
        re.IGNORECASE,
    )
    _ENCRYPTION_PATTERN = re.compile(r"\b(encrypt|tls|https://|fernet|kms|cipher)\b", re.IGNORECASE)
    _LOGGING_PATTERN = re.compile(r"\b(logging\.|logger\.|audit|trace_id|structlog)\b", re.IGNORECASE)
    _ACCESS_CONTROL_PATTERN = re.compile(r"\b(auth|authorize|permission|role|rbac|oauth|jwt)\b", re.IGNORECASE)
    _EVAL_PATTERN = re.compile(r"\beval\s*\(")

    def evaluate(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        findings.extend(self._check_gdpr(output_code))
        findings.extend(self._check_iso27001(output_code))
        findings.extend(self._check_custom_policies(output_code))
        return findings

    def _check_gdpr(self, output_code: str) -> List[Finding]:
        if self._PERSONAL_DATA_PATTERN.search(output_code) and not self._ENCRYPTION_PATTERN.search(output_code):
            return [
                Finding(
                    pillar="COMPLIANCE",
                    severity="HIGH",
                    category="GDPR",
                    description="Personal data handling detected without an explicit encryption or transport-security control.",
                    recommendation="Document lawful processing and add encryption in transit/at rest for personal data flows.",
                )
            ]
        return []

    def _check_iso27001(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        if not self._LOGGING_PATTERN.search(output_code):
            findings.append(
                Finding(
                    pillar="COMPLIANCE",
                    severity="MEDIUM",
                    category="ISO27001_LOGGING",
                    description="No audit-friendly logging controls detected.",
                    recommendation="Add structured security or operational logging for critical flows.",
                )
            )
        if not self._ACCESS_CONTROL_PATTERN.search(output_code):
            findings.append(
                Finding(
                    pillar="COMPLIANCE",
                    severity="MEDIUM",
                    category="ISO27001_ACCESS_CONTROL",
                    description="No access-control or authorization checks detected.",
                    recommendation="Enforce authentication/authorization for sensitive operations.",
                )
            )
        return findings

    def _check_custom_policies(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(output_code.splitlines(), start=1):
            if self._EVAL_PATTERN.search(line):
                findings.append(
                    Finding(
                        pillar="COMPLIANCE",
                        severity="HIGH",
                        category="CUSTOM_POLICY",
                        description="Policy violation: use of eval() is not allowed.",
                        line=index,
                        recommendation="Replace eval() with explicit parsing or a whitelist-based dispatcher.",
                    )
                )
        return findings
