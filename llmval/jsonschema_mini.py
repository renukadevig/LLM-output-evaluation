"""A tiny dependency-free JSON Schema validator.

Supports the subset that actually matters for validating structured LLM output:
type, required, properties, items, enum, const, additionalProperties (bool),
minLength/maxLength, minimum/maximum, minItems/maxItems. Returns a list of
human-readable error strings ([] == valid). Not a full Draft-7 implementation —
if you need that, `pip install jsonschema` and swap this out.
"""
from __future__ import annotations

from typing import Any

_TYPES = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
}


def validate(data: Any, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        # bool is a subclass of int — reject it where a number/integer is wanted
        ok = False
        for tt in types:
            py = _TYPES.get(tt)
            if py is None:
                continue
            if tt in ("integer", "number") and isinstance(data, bool):
                continue
            if isinstance(data, py):
                ok = True
                break
        if not ok:
            errs.append(f"{path}: expected type {t}, got {type(data).__name__}")
            return errs  # further checks are unreliable once the type is wrong

    if "const" in schema and data != schema["const"]:
        errs.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: {data!r} not in enum {schema['enum']}")

    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errs.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errs.append(f"{path}: longer than maxLength {schema['maxLength']}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errs.append(f"{path}: above maximum {schema['maximum']}")

    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                errs.append(f"{path}: missing required property '{req}'")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in data:
                errs += validate(data[key], sub, f"{path}.{key}")
        addl = schema.get("additionalProperties", True)
        if addl is False:
            extra = [k for k in data if k not in props]
            if extra:
                errs.append(f"{path}: unexpected properties {extra}")

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errs.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errs.append(f"{path}: more than maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(data):
                errs += validate(item, item_schema, f"{path}[{i}]")

    return errs
