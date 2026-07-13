"""Embedding-based *semantic* similarity (optional, pluggable).

`similarity` in evaluators.py is lexical (token overlap). This adds a
`semantic_similarity` check that compares meaning via real embeddings, so
"refunds take five days" and "reimbursements complete in a work week" score high
even with no shared tokens.

Backends, auto-detected in this order (or force with `backend:` in the check):
  * "sentence_transformers" — fully local, offline. `pip install sentence-transformers`
        model default: all-MiniLM-L6-v2
  * "openai" — needs `pip install openai` and OPENAI_API_KEY in the env.
        model default: text-embedding-3-small

If no backend is available the check is reported SKIP (never FAIL) — the same
honesty rule the judge uses for an un-measured dimension.
"""
from __future__ import annotations

import math
import os
from typing import Callable

from .core import CheckResult, EvalContext, SKIP
from .evaluators import _res, evaluator

# cache loaded models / clients across cases (keyed by backend+model)
_CACHE: dict[str, Callable[[str], list[float]]] = {}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _sentence_transformers_embedder(model_name: str):
    from sentence_transformers import SentenceTransformer  # type: ignore
    model = SentenceTransformer(model_name)

    def embed(text: str) -> list[float]:
        return model.encode(text, normalize_embeddings=False).tolist()

    return embed


def _openai_embedder(model_name: str):
    from openai import OpenAI  # type: ignore
    client = OpenAI()  # reads OPENAI_API_KEY

    def embed(text: str) -> list[float]:
        resp = client.embeddings.create(model=model_name, input=text)
        return resp.data[0].embedding

    return embed


_DEFAULT_MODELS = {
    "sentence_transformers": "all-MiniLM-L6-v2",
    "openai": "text-embedding-3-small",
}


def _get_embedder(backend: str | None, model: str | None) -> tuple[str, Callable | None, str]:
    """Return (backend_used, embed_fn_or_None, message)."""
    order = [backend] if backend else ["sentence_transformers", "openai"]
    last = "no embedding backend requested"
    for be in order:
        if be == "openai" and not os.environ.get("OPENAI_API_KEY"):
            last = "openai backend needs OPENAI_API_KEY"
            continue
        m = model or _DEFAULT_MODELS.get(be, model or "")
        key = f"{be}:{m}"
        if key in _CACHE:
            return be, _CACHE[key], ""
        try:
            if be == "sentence_transformers":
                fn = _sentence_transformers_embedder(m)
            elif be == "openai":
                fn = _openai_embedder(m)
            else:
                last = f"unknown backend '{be}'"
                continue
        except ImportError:
            last = (f"{be} not installed "
                    f"(pip install {'sentence-transformers' if be.startswith('sentence') else be})")
            continue
        except Exception as e:  # noqa: BLE001 — model load / auth failure → skip, don't crash
            last = f"{be} unavailable: {e}"
            continue
        _CACHE[key] = fn
        return be, fn, ""
    return backend or "auto", None, last


@evaluator("semantic_similarity")
def _semantic_similarity(check: dict, ctx: EvalContext) -> CheckResult:
    ref = check.get("reference", ctx.reference)
    required = bool(check.get("required", True))
    weight = float(check.get("weight", 1.0))
    if not ref:
        return CheckResult(type="semantic_similarity", status="error", score=0.0,
                           weight=weight, required=required, reason="no reference provided")

    be, embed, msg = _get_embedder(check.get("backend"), check.get("model"))
    if embed is None:
        return CheckResult(type="semantic_similarity", status=SKIP, score=1.0,
                           weight=weight, required=required,
                           reason=f"skipped — {msg}")

    try:
        score = _cosine(embed(ctx.output), embed(ref))
    except Exception as e:  # noqa: BLE001
        return CheckResult(type="semantic_similarity", status=SKIP, score=1.0,
                           weight=weight, required=required,
                           reason=f"skipped — embedding failed: {e}")

    thr = float(check.get("min_score", 0.75))
    return _res(check, score >= thr,
                f"[{be}] semantic similarity {score:.3f} (min {thr})",
                score=score, measured=round(score, 4), backend=be)
