"""llmval — a portable, project-agnostic LLM output validation framework.

Validate structured *and* unstructured LLM output against a declarative suite:
deterministic checks (format/schema/regex), lexical similarity, and an optional
LLM-as-judge (local `claude` CLI, no API key). Stdlib-only core, runs offline.

    python3 -m llmval run suite.yaml
    python3 -m llmval run suite.yaml --no-judge --format junit -o results.xml
"""

from .core import CaseResult, CheckResult, EvalContext, SuiteResult
from .suite import JudgeConfig, Suite, load_suite
from .runner import run_suite

__version__ = "0.1.0"

__all__ = [
    "CaseResult", "CheckResult", "EvalContext", "SuiteResult",
    "JudgeConfig", "Suite", "load_suite", "run_suite", "__version__",
]
