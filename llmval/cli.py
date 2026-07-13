"""Command-line entry point: `python3 -m llmval run <suite>`."""
from __future__ import annotations

import argparse
import sys

from .report import render
from .runner import run_suite
from .suite import load_suite


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="llmval",
        description="Validate structured & unstructured LLM output against a declarative suite.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a validation suite")
    r.add_argument("suite", help="path to a .yaml/.yml/.json suite file")
    r.add_argument("--no-judge", action="store_true", help="disable the LLM judge (fully offline)")
    r.add_argument("--cli-path", default=None, help="path to the claude CLI (default: 'claude')")
    r.add_argument("--format", choices=["text", "json", "junit"], default="text")
    r.add_argument("-o", "--output", default=None, help="write report to a file instead of stdout")
    r.add_argument("--fail-under", type=float, default=None,
                   help="exit non-zero if pass rate < N (0..1); default requires all cases to pass")

    lst = sub.add_parser("checks", help="list available check types")

    args = p.parse_args(argv)

    if args.cmd == "checks":
        from .evaluators import REGISTRY
        import llmval.judge  # noqa: F401 — register the judge
        import llmval.embeddings  # noqa: F401 — register semantic_similarity
        for name in sorted(REGISTRY):
            print(name)
        return 0

    suite = load_suite(args.suite)
    if args.no_judge:
        suite.judge.backend = "none"
    if args.cli_path:
        suite.judge.cli_path = args.cli_path

    result = run_suite(suite)
    text = render(result, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.format} report to {args.output}", file=sys.stderr)
    else:
        print(text)

    if args.fail_under is not None:
        return 0 if result.pass_rate >= args.fail_under else 1
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
