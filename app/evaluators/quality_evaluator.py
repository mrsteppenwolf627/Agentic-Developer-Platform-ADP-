"""Code quality checks for generated outputs."""
from __future__ import annotations

import ast
import re
from typing import List

from app.evaluators.security_evaluator import Finding


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_complexities: list[tuple[str, int, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node)
        self.generic_visit(node)

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                    ast.BoolOp,
                    ast.IfExp,
                    ast.Try,
                    ast.Match,
                ),
            ):
                complexity += 1
        self.function_complexities.append((node.name, complexity, node.lineno))


class QualityEvaluator:
    """Heuristic quality gate for type safety, tests, linting and complexity."""

    _TYPE_HINT_PATTERN = re.compile(
        r"(def .+\)\s*->|:\s*[A-Z][A-Za-z0-9_\[\], ]+|BaseModel|Field\()",
        re.IGNORECASE,
    )
    _TS_TYPE_PATTERN = re.compile(
        r"(interface\s+\w+|type\s+\w+\s*=|:\s*(string|number|boolean|Record<|Promise<))"
    )
    _TEST_PATTERN = re.compile(r"\b(def\s+test_|it\s*\(|describe\s*\(|pytest|unittest)\b", re.IGNORECASE)
    _ASSERT_PATTERN = re.compile(r"\b(assert |expect\s*\()")
    _LINT_VIOLATIONS = [
        (
            re.compile(r"^.{101,}$"),
            "MEDIUM",
            "LINT",
            "Line exceeds 100 characters and is likely to fail common formatters/linters.",
            "Wrap the expression or extract intermediate variables.",
        ),
        (
            re.compile(r"\bprint\s*\("),
            "MEDIUM",
            "LINT",
            "Debug print statement detected.",
            "Use structured logging instead of print().",
        ),
        (
            re.compile(r"\bconsole\.log\s*\("),
            "MEDIUM",
            "LINT",
            "Debug console logging detected.",
            "Remove console logging or replace it with the project logging abstraction.",
        ),
    ]

    def evaluate(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        findings.extend(self._check_type_safety(output_code))
        findings.extend(self._check_test_coverage(output_code))
        findings.extend(self._check_linting(output_code))
        findings.extend(self._check_complexity(output_code))
        return findings

    def _check_type_safety(self, output_code: str) -> List[Finding]:
        has_python_function = "def " in output_code
        has_typescript_shape = any(
            token in output_code for token in ("interface ", "type ", ": string", ": number", ": boolean")
        )
        typed_enough = bool(self._TYPE_HINT_PATTERN.search(output_code) or self._TS_TYPE_PATTERN.search(output_code))

        if (has_python_function or has_typescript_shape) and not typed_enough:
            return [
                Finding(
                    pillar="CODE_QUALITY",
                    severity="HIGH",
                    category="TYPE_SAFETY",
                    description="Generated code lacks explicit type annotations or schema coverage.",
                    recommendation="Add Python type hints, Pydantic models, or TypeScript interfaces for public inputs and outputs.",
                )
            ]
        return []

    def _check_test_coverage(self, output_code: str) -> List[Finding]:
        if not self._TEST_PATTERN.search(output_code):
            return []

        function_count = len(re.findall(r"\b(def|function)\s+\w+", output_code))
        assertion_count = len(self._ASSERT_PATTERN.findall(output_code))
        if function_count <= 0:
            return []

        estimated_coverage = min(1.0, assertion_count / function_count)
        if estimated_coverage < 0.8:
            return [
                Finding(
                    pillar="CODE_QUALITY",
                    severity="MEDIUM",
                    category="TEST_COVERAGE",
                    description=f"Estimated test coverage is below 80% ({estimated_coverage:.2f}).",
                    recommendation="Expand tests to cover happy path, errors, and edge cases until coverage is at least 0.80.",
                )
            ]
        return []

    def _check_linting(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(output_code.splitlines(), start=1):
            for pattern, severity, category, description, recommendation in self._LINT_VIOLATIONS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            pillar="CODE_QUALITY",
                            severity=severity,
                            category=category,
                            description=description,
                            line=index,
                            recommendation=recommendation,
                        )
                    )
        return findings

    def _check_complexity(self, output_code: str) -> List[Finding]:
        if not any(token in output_code for token in ("def ", "async def ")):
            return []

        try:
            tree = ast.parse(output_code)
        except SyntaxError:
            return [
                Finding(
                    pillar="CODE_QUALITY",
                    severity="HIGH",
                    category="SYNTAX",
                    description="Generated Python code is not syntactically valid, blocking quality tooling.",
                    recommendation="Fix syntax errors before running Black, Pylint, or tests.",
                )
            ]

        visitor = _ComplexityVisitor()
        visitor.visit(tree)

        findings: List[Finding] = []
        for function_name, complexity, lineno in visitor.function_complexities:
            if complexity >= 10:
                findings.append(
                    Finding(
                        pillar="CODE_QUALITY",
                        severity="MEDIUM",
                        category="CYCLOMATIC_COMPLEXITY",
                        description=f"Function '{function_name}' exceeds the complexity threshold ({complexity} >= 10).",
                        line=lineno,
                        recommendation="Split the function into smaller units or simplify branching.",
                    )
                )
        return findings
