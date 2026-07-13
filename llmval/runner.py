"""Orchestration: resolve each case's output, run its checks, collect results."""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any

from .core import CaseResult, EvalContext, SuiteResult
from .evaluators import dispatch
from . import judge as _judge  # noqa: F401  (self-registers the "judge" evaluator)
from . import embeddings as _embeddings  # noqa: F401  (self-registers "semantic_similarity")
from .suite import Suite


def _read_file(base_dir: str, rel: str) -> str:
    with open(os.path.join(base_dir, rel), "r", encoding="utf-8") as f:
        return f.read()


def _run_command(command: Any, base_dir: str, timeout: int, shell: bool) -> str:
    args = command if shell else (command if isinstance(command, list) else shlex.split(command))
    proc = subprocess.run(
        args, cwd=base_dir, capture_output=True, text=True,
        timeout=timeout, shell=shell,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def _resolve_source(case: dict, key: str, base_dir: str, cmd_key: str | None = None):
    """Resolve one text input from `<key>` (inline), `<key>_file`, or
    `<key>_command` (runs it, uses stdout). The command form is what lets a
    reference/context be fetched from a live API, e.g.
        reference_command: "curl -s https://api/orders/5512 | jq -r .eta"
    Returns None if no source is given for this key."""
    if key in case:
        return str(case[key])
    if f"{key}_file" in case:
        return _read_file(base_dir, case[f"{key}_file"])
    # accept both the explicit cmd_key (e.g. "command" for output) and "<key>_command"
    for ck in ([cmd_key] if cmd_key else []) + [f"{key}_command"]:
        if ck in case:
            return _run_command(
                case[ck], base_dir,
                timeout=int(case.get("timeout", 120)),
                shell=bool(case.get("shell", False)),
            )
    return None


def _resolve_output(case: dict, base_dir: str) -> str:
    v = _resolve_source(case, "output", base_dir, cmd_key="command")
    if v is None:
        raise ValueError("case has no output source (need one of: output, output_file, command)")
    return v


def _resolve_text(case: dict, key: str, base_dir: str) -> str:
    v = _resolve_source(case, key, base_dir)
    return v if v is not None else ""


def run_case(case: dict, suite: Suite) -> CaseResult:
    name = case.get("name", "<unnamed>")
    try:
        output = _resolve_output(case, suite.base_dir)
    except Exception as e:  # noqa: BLE001 — surface any resolution failure as a case error
        return CaseResult(name=name, error=str(e))

    ctx = EvalContext(
        output=output,
        context=_resolve_text(case, "context", suite.base_dir),
        reference=_resolve_text(case, "reference", suite.base_dir),
        prompt=_resolve_text(case, "prompt", suite.base_dir),
        judge=suite.judge,
        base_dir=suite.base_dir,
    )

    result = CaseResult(name=name, output=output)
    for check in case.get("checks", []):
        merged = {**suite.defaults, **check}
        result.checks.append(dispatch(merged, ctx))
    return result


def run_suite(suite: Suite) -> SuiteResult:
    return SuiteResult(name=suite.name, cases=[run_case(c, suite) for c in suite.cases])
