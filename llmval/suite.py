"""Suite loading. Accepts YAML (if PyYAML is installed) or JSON."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeConfig:
    backend: str = "cli"          # "cli" | "none"
    cli_path: str = "claude"
    timeout: int = 180


@dataclass
class Suite:
    name: str
    cases: list[dict[str, Any]] = field(default_factory=list)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    defaults: dict[str, Any] = field(default_factory=dict)
    base_dir: str = "."


def _read(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise SystemExit(
                f"'{path}' is YAML but PyYAML is not installed.\n"
                f"  pip install pyyaml   — or convert the suite to .json"
            ) from e
        return yaml.safe_load(text)
    return json.loads(text)


def load_suite(path: str) -> Suite:
    raw = _read(path)
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: suite must be a mapping at the top level")
    j = raw.get("judge", {}) or {}
    judge = JudgeConfig(
        backend=j.get("backend", "cli"),
        cli_path=j.get("cli_path", "claude"),
        timeout=int(j.get("timeout", 180)),
    )
    return Suite(
        name=raw.get("name", os.path.basename(path)),
        cases=raw.get("cases", []),
        judge=judge,
        defaults=raw.get("defaults", {}),
        base_dir=os.path.dirname(os.path.abspath(path)) or ".",
    )
