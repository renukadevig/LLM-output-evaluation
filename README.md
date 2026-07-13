# llmval — LLM output validation framework

A portable, **project-agnostic** way to validate LLM output — **structured**
(JSON schema, field assertions, exact labels) *and* **unstructured** (similarity,
keyword recall, LLM-as-judge). You describe *what* to check in a declarative
suite; `llmval` runs it and reports pass/fail.

- **Stdlib-only core** — copy the `llmval/` folder into any project, no install.
- **Judge via the local `claude` CLI** — no API key. `--no-judge` runs fully offline.
- **Works with any language/project** — feed it output inline, from a file, or by
  running a command (`command:`), so the thing under test can be anything.
- **CI-ready** — text / JSON / JUnit-XML output and a `--fail-under` exit gate.

Generalized from the `backend/governance/` module (evidence-first judging, honest
"skip" for un-measured dimensions, anti-gaming discipline).

## Quick start

```bash
cd llm-validator

python3 -m llmval run examples/example_suite.json --no-judge   # fully offline
python3 -m llmval run examples/example_suite.json              # + LLM judge
python3 -m llmval checks                                        # list check types
python3 -m unittest discover -s tests                          # run the tests
```

## How it works

```
case → resolve output (inline | file | command)
     → run each check → status (pass/fail/skip/error) + 0..1 score
     → case passes iff every REQUIRED check passes
suite → all cases pass → exit 0
```

Three layers, cheapest first — a `skip` (e.g. judge disabled) never fails a case:

| Layer | Check types | Cost |
|---|---|---|
| Deterministic | `contains` `not_contains` `regex` `equals` `one_of` `min_length` `max_length` `json_valid` `json_schema` `json_path` `no_refusal` `no_pii` | free |
| Lexical similarity | `similarity` (cosine/jaccard) · `keyword_recall` | cheap |
| Semantic similarity | `semantic_similarity` (real embeddings) | model/API |
| LLM-as-judge | `judge` (rubric: `faithfulness` `relevance` `correctness` `coherence` `tone` `conciseness` `safety`, or free text) | CLI call |

## Sample data

Runnable out of the box in `examples/` — try these first:

```bash
python3 -m llmval run examples/example_suite.json          --no-judge   # 5 cases, all pass
python3 -m llmval run examples/example_suite.yaml          --no-judge   # inline + file + command sources
python3 -m llmval run examples/sample_suite_with_failures.json --no-judge # mixed pass/fail — see a real report
```

- `example_suite.json` / `.yaml` — one suite showing every output source (inline, `output_file`, `command`) and both structured & unstructured checks.
- `sample_suite_with_failures.json` — a small labeled dataset where several cases fail on purpose (bad schema type, out-of-set label, PII leak, refusal) so you can see how failures render.
- `fixtures/` — sample source + summary text used by the RAG/faithfulness case.
- `demo_extractor.py` — a stand-in "LLM call" for the `command:` example; replace with your real model call.

## Suite format

YAML (needs `pip install pyyaml`) or JSON. Each case needs one **output source**
and a list of **checks**:

```yaml
name: my suite
judge: { backend: cli, cli_path: claude }   # or backend: none
defaults: { case_insensitive: true }        # merged into every check
cases:
  - name: structured extraction
    command: "python3 my_extractor.py 'John is 30'"   # output = stdout
    checks:
      - { type: json_valid }
      - type: json_schema
        schema: { type: object, required: [name, age],
                  properties: { name: {type: string}, age: {type: integer} } }
      - { type: json_path, path: age, equals: 30 }

  - name: rag answer stays faithful
    output_file: out/answer.txt        # or: output: "inline text"
    context_file: docs/source.txt      # ground truth for the judge
    checks:
      - { type: max_length, value: 80, unit: words }
      - { type: judge, rubric: faithfulness, min_score: 4 }
```

**Output sources** (pick one per case): `output:` (inline) · `output_file:` ·
`command:` (runs it, captures stdout; add `shell: true` for pipes).
**Context inputs** for the judge/similarity: `context`/`context_file`,
`reference`/`reference_file`, `prompt`/`prompt_file`.

**Common check keys:** `weight` (score weighting), `required: false` (report but
don't fail the case).

## Semantic similarity (embeddings)

`similarity` is lexical (shared tokens). `semantic_similarity` compares *meaning*
via real embeddings, so paraphrases score high with no shared words. It needs one
optional backend; without one it reports `skip` (never fails):

```bash
pip install sentence-transformers      # local, offline (default backend)
# or
pip install openai && export OPENAI_API_KEY=...   # OpenAI embeddings backend
```

```yaml
- type: semantic_similarity
  reference: "Refunds complete in about a work week."
  min_score: 0.8
  # backend: sentence_transformers | openai   (auto-detected if omitted)
  # model:   all-MiniLM-L6-v2 | text-embedding-3-small
```

## Installation

Zero-install: copy `llmval/` and run `python3 -m llmval`. Or install the CLI:

```bash
pip install -e .                 # gives you the `llmval` command
pip install -e ".[embeddings]"   # + local semantic similarity
pip install -e ".[yaml]"         # + YAML suite support
```

## Adding your own check

```python
from llmval.evaluators import evaluator, _res

@evaluator("starts_with")
def _starts_with(check, ctx):
    ok = ctx.output.lstrip().startswith(check["value"])
    return _res(check, ok, f"starts with {check['value']!r}: {ok}")
```

Import your module before running and the new `type` is available in any suite.

## CI

```bash
python3 -m llmval run suite.yaml --no-judge --format junit -o results.xml
python3 -m llmval run suite.yaml --fail-under 0.9   # exit 1 if <90% pass
```

## Layout

```
llmval/
  core.py            data model (CheckResult / CaseResult / SuiteResult, statuses)
  suite.py           suite loader (YAML/JSON) + JudgeConfig
  evaluators.py      deterministic + similarity checks, the @evaluator registry
  judge.py           LLM-as-judge via local claude CLI (self-registers)
  jsonschema_mini.py dependency-free JSON Schema subset validator
  runner.py          resolve output → run checks
  report.py          text / json / junit rendering
  cli.py             `run`, `checks`
examples/            runnable JSON + YAML suites, a demo extractor
tests/               offline unit tests (no CLI needed)
```

## Scope / caveats

- `similarity` is **lexical** (token cosine/jaccard). For semantic similarity,
  use the `judge`, or register an embedding-backed evaluator.
- The judge is only as reliable as the rubric — calibrate against a few
  human-labeled cases, and prefer a different model to judge than the one tested.
- Advisory by design: a report is triage signal; wire `--fail-under` into CI when
  you want it to gate.
```
