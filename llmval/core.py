"""Core data model.

A suite has cases; a case produces one output and runs many checks against it.
Every check reports a *status* (pass/fail/skip/error) plus a normalized 0..1
score. `skip` means "not evaluated" (e.g. judge disabled) — it never fails a
case, mirroring the governance module's honesty about un-measured dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PASS, FAIL, SKIP, ERROR = "pass", "fail", "skip", "error"


@dataclass
class CheckResult:
    type: str
    status: str                       # PASS | FAIL | SKIP | ERROR
    score: float = 1.0                # 0..1 (1/0 for boolean checks)
    weight: float = 1.0
    required: bool = True
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (PASS, SKIP)


@dataclass
class CaseResult:
    name: str
    output: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.error:
            return ERROR
        if any(c.status == ERROR for c in self.checks):
            return ERROR
        if any(c.status == FAIL for c in self.checks if c.required):
            return FAIL
        return PASS

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def score(self) -> float:
        """Weighted mean over checks that were actually evaluated."""
        scored = [c for c in self.checks if c.status in (PASS, FAIL)]
        if not scored:
            return 1.0
        tw = sum(c.weight for c in scored) or 1.0
        return sum(c.score * c.weight for c in scored) / tw


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total if self.total else 1.0

    @property
    def mean_score(self) -> float:
        return sum(c.score for c in self.cases) / self.total if self.total else 1.0


@dataclass
class EvalContext:
    """Everything a check needs about one candidate output."""
    output: str
    context: str = ""                 # grounding / source text (for faithfulness)
    reference: str = ""               # golden answer (for similarity/correctness)
    prompt: str = ""                  # the input given to the model, if known
    judge: Any = None                 # JudgeConfig | None
    base_dir: str = "."
