"""Rendering: text (human), json (machine), junit (CI)."""
from __future__ import annotations

import json
from dataclasses import asdict
from xml.sax.saxutils import escape, quoteattr

from .core import ERROR, FAIL, PASS, SKIP, SuiteResult

_MARK = {PASS: "PASS", FAIL: "FAIL", SKIP: "skip", ERROR: "ERR "}
_CHECK_MARK = {PASS: "✓", FAIL: "✗", SKIP: "–", ERROR: "!"}


def render(result: SuiteResult, fmt: str = "text") -> str:
    if fmt == "json":
        return _json(result)
    if fmt == "junit":
        return _junit(result)
    return _text(result)


def _text(r: SuiteResult) -> str:
    lines = [f"Suite: {r.name}", "=" * (7 + len(r.name)), ""]
    for case in r.cases:
        lines.append(f"[{_MARK[case.status]}] {case.name}  (score {case.score:.2f})")
        if case.error:
            lines.append(f"      ! {case.error}")
        for c in case.checks:
            lines.append(f"      {_CHECK_MARK[c.status]} {c.type}: {c.reason}")
        lines.append("")
    lines.append(
        f"{r.passed_count}/{r.total} cases passed "
        f"(pass rate {r.pass_rate:.0%}, mean score {r.mean_score:.2f})"
    )
    lines.append("RESULT: PASS" if r.passed else "RESULT: FAIL")
    return "\n".join(lines)


def _json(r: SuiteResult) -> str:
    payload = {
        "name": r.name,
        "passed": r.passed,
        "total": r.total,
        "passed_count": r.passed_count,
        "pass_rate": round(r.pass_rate, 4),
        "mean_score": round(r.mean_score, 4),
        "cases": [
            {
                "name": c.name,
                "status": c.status,
                "score": round(c.score, 4),
                "error": c.error,
                "checks": [asdict(ch) for ch in c.checks],
            }
            for c in r.cases
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _junit(r: SuiteResult) -> str:
    failures = sum(1 for c in r.cases if c.status == FAIL)
    errors = sum(1 for c in r.cases if c.status == ERROR)
    out = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append(
        f'<testsuite name={quoteattr(r.name)} tests="{r.total}" '
        f'failures="{failures}" errors="{errors}">'
    )
    for c in r.cases:
        out.append(f'  <testcase name={quoteattr(c.name)}>')
        if c.status == ERROR:
            out.append(f'    <error message={quoteattr(c.error or "error")}/>')
        elif c.status == FAIL:
            msg = "; ".join(f"{ch.type}: {ch.reason}" for ch in c.checks if ch.status == FAIL)
            out.append(f'    <failure message={quoteattr(msg)}>{escape(msg)}</failure>')
        out.append("  </testcase>")
    out.append("</testsuite>")
    return "\n".join(out)
