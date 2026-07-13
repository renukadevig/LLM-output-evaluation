"""The check registry: deterministic + lexical-similarity evaluators.

Each evaluator is `fn(check: dict, ctx: EvalContext) -> CheckResult` registered
under a `type` name. Add your own with the `@evaluator("my_type")` decorator.
The judge evaluator lives in judge.py and self-registers on import.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .core import CheckResult, EvalContext, FAIL, PASS
from . import jsonschema_mini

REGISTRY: dict[str, Callable[[dict, EvalContext], CheckResult]] = {}


def evaluator(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


def _res(check: dict, ok: bool, reason: str, score: float | None = None, **detail) -> CheckResult:
    return CheckResult(
        type=check.get("type", "?"),
        status=PASS if ok else FAIL,
        score=(1.0 if ok else 0.0) if score is None else float(score),
        weight=float(check.get("weight", 1.0)),
        required=bool(check.get("required", True)),
        reason=reason,
        detail=detail,
    )


def dispatch(check: dict, ctx: EvalContext) -> CheckResult:
    t = check.get("type")
    fn = REGISTRY.get(t)
    if fn is None:
        return CheckResult(type=t or "?", status="error", score=0.0,
                           required=bool(check.get("required", True)),
                           reason=f"unknown check type '{t}'")
    return fn(check, ctx)


# ----------------------------- helpers -------------------------------------

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _extract_json_text(text: str) -> str:
    """Strip ```json fences and grab the first balanced object/array."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    return m.group(1) if m else text.strip()


def _parse_json(text: str) -> Any:
    return json.loads(_extract_json_text(text))


def _resolve_path(data: Any, path: str) -> tuple[bool, Any]:
    """Dotted path with list indices, e.g. 'items.0.name'."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return False, None
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


# --------------------------- deterministic ---------------------------------

@evaluator("contains")
def _contains(check, ctx):
    vals = check["value"]
    vals = vals if isinstance(vals, list) else [vals]
    hay = ctx.output.lower() if check.get("case_insensitive", True) else ctx.output
    hits = [v for v in vals if (str(v).lower() if check.get("case_insensitive", True) else str(v)) in hay]
    mode = check.get("mode", "all")
    ok = len(hits) == len(vals) if mode == "all" else len(hits) > 0
    return _res(check, ok, f"found {hits or 'none'} of {vals} (mode={mode})")


@evaluator("not_contains")
def _not_contains(check, ctx):
    vals = check["value"]
    vals = vals if isinstance(vals, list) else [vals]
    hay = ctx.output.lower() if check.get("case_insensitive", True) else ctx.output
    hits = [v for v in vals if (str(v).lower() if check.get("case_insensitive", True) else str(v)) in hay]
    return _res(check, not hits, f"forbidden present: {hits}" if hits else "no forbidden substrings")


@evaluator("regex")
def _regex(check, ctx):
    flags = re.IGNORECASE if check.get("case_insensitive", False) else 0
    matched = bool(re.search(check["pattern"], ctx.output, flags | re.DOTALL))
    should = check.get("should_match", True)
    return _res(check, matched == should,
                f"pattern {'matched' if matched else 'did not match'} (wanted match={should})")


@evaluator("equals")
def _equals(check, ctx):
    # `value` is a literal; omit it to compare against the reference (which may be
    # fetched from an API via reference_command) — i.e. "output == API's value".
    if "value" in check:
        b = str(check["value"])
    elif ctx.reference:
        b = ctx.reference
    else:
        return CheckResult(type="equals", status="error", score=0.0,
                           required=bool(check.get("required", True)),
                           reason="equals needs 'value' or a reference to compare against")
    a, b = ctx.output.strip(), b.strip()
    if check.get("case_insensitive", False):
        a, b = a.lower(), b.lower()
    return _res(check, a == b, "exact match" if a == b else f"expected {b!r}, got {a!r}")


@evaluator("one_of")
def _one_of(check, ctx):
    opts = [str(o) for o in check["value"]]
    val = ctx.output.strip()
    if check.get("case_insensitive", False):
        opts = [o.lower() for o in opts]
        val = val.lower()
    return _res(check, val in opts, f"{val!r} in {opts}" if val in opts else f"{val!r} not in {opts}")


@evaluator("min_length")
def _min_length(check, ctx):
    unit = check.get("unit", "chars")
    n = len(_tokens(ctx.output)) if unit == "words" else len(ctx.output)
    return _res(check, n >= check["value"], f"length {n} {unit} (min {check['value']})")


@evaluator("max_length")
def _max_length(check, ctx):
    unit = check.get("unit", "chars")
    n = len(_tokens(ctx.output)) if unit == "words" else len(ctx.output)
    return _res(check, n <= check["value"], f"length {n} {unit} (max {check['value']})")


@evaluator("json_valid")
def _json_valid(check, ctx):
    try:
        _parse_json(ctx.output)
        return _res(check, True, "valid JSON")
    except (json.JSONDecodeError, ValueError) as e:
        return _res(check, False, f"invalid JSON: {e}")


@evaluator("json_schema")
def _json_schema(check, ctx):
    try:
        data = _parse_json(ctx.output)
    except (json.JSONDecodeError, ValueError) as e:
        return _res(check, False, f"invalid JSON: {e}")
    errs = jsonschema_mini.validate(data, check["schema"])
    return _res(check, not errs, "schema valid" if not errs else "; ".join(errs[:5]), errors=errs)


@evaluator("json_path")
def _json_path(check, ctx):
    try:
        data = _parse_json(ctx.output)
    except (json.JSONDecodeError, ValueError) as e:
        return _res(check, False, f"invalid JSON: {e}")
    found, val = _resolve_path(data, check["path"])
    if not found:
        return _res(check, False, f"path '{check['path']}' not found")
    if "equals" in check:
        return _res(check, val == check["equals"],
                    f"{check['path']}={val!r} (wanted {check['equals']!r})")
    if check.get("equals_ref"):
        # compare the extracted field against the reference (e.g. an API value)
        want = ctx.reference.strip()
        got = str(val).strip()
        return _res(check, got == want,
                    f"{check['path']}={got!r} vs reference {want!r}")
    if "type" in check:
        py = jsonschema_mini._TYPES.get(check["type"])
        ok = isinstance(val, py) and not (check["type"] in ("integer", "number") and isinstance(val, bool))
        return _res(check, ok, f"{check['path']} is {type(val).__name__} (wanted {check['type']})")
    return _res(check, True, f"path '{check['path']}' exists = {val!r}")


_REFUSAL = re.compile(
    r"\b(i (?:can(?:'|no)?t|cannot|won'?t|am unable to|am not able to)|"
    r"i'?m (?:sorry|unable)|as an ai|i do not have the ability)\b", re.IGNORECASE)


@evaluator("no_refusal")
def _no_refusal(check, ctx):
    m = _REFUSAL.search(ctx.output)
    return _res(check, not m, f"refusal-like phrase: {m.group(0)!r}" if m else "no refusal detected")


_PII = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"\b(?:\+?\d[\d ().-]{7,}\d)\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


@evaluator("no_pii")
def _no_pii(check, ctx):
    kinds = check.get("kinds", list(_PII))
    found = [k for k in kinds if k in _PII and _PII[k].search(ctx.output)]
    return _res(check, not found, f"PII detected: {found}" if found else "no PII detected", found=found)


# ---------------------------- similarity -----------------------------------

def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def _cosine(a: str, b: str) -> float:
    from collections import Counter
    import math
    ca, cb = Counter(_tokens(a)), Counter(_tokens(b))
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    dot = sum(ca[t] * cb[t] for t in common)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


@evaluator("similarity")
def _similarity(check, ctx):
    ref = check.get("reference", ctx.reference)
    if not ref:
        return CheckResult(type="similarity", status="error", score=0.0,
                           required=bool(check.get("required", True)),
                           reason="no reference provided")
    method = check.get("method", "cosine")
    score = _cosine(ctx.output, ref) if method == "cosine" else _jaccard(ctx.output, ref)
    thr = float(check.get("min_score", 0.7))
    ok = score >= thr
    return _res(check, ok, f"{method} similarity {score:.3f} (min {thr})", score=score,
                measured=round(score, 4))


@evaluator("keyword_recall")
def _keyword_recall(check, ctx):
    kws = check["keywords"]
    ci = check.get("case_insensitive", True)
    hay = ctx.output.lower() if ci else ctx.output
    present = [k for k in kws if (k.lower() if ci else k) in hay]
    ratio = len(present) / len(kws) if kws else 1.0
    thr = float(check.get("min_ratio", 1.0))
    ok = ratio >= thr
    missing = [k for k in kws if k not in present]
    return _res(check, ok, f"recall {ratio:.2f} (min {thr}); missing {missing}", score=ratio,
                missing=missing)
