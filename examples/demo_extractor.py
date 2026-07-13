#!/usr/bin/env python3
"""A stand-in for "your project's LLM call". Prints structured JSON to stdout so
the `command:` source in example_suite.yaml has something to validate. Replace
this with a real invocation of your app/model."""
import json
import re
import sys

text = sys.argv[1] if len(sys.argv) > 1 else ""
name = (re.search(r"^([A-Z][a-z]+)", text) or [None, None])[1]
age = (re.search(r"\b(\d{1,3})\b", text) or [None, None])[1]
email = (re.search(r"[\w.+-]+@[\w.-]+", text) or [None])[0]

print(json.dumps({
    "name": name,
    "age": int(age) if age else None,
    "email": email,
}))
