# llmval — LLM output validation framework

A portable, **project-agnostic** way to validate LLM output — **structured**
(JSON schema, field assertions, exact labels) *and* **unstructured** (lexical +
semantic similarity, LLM-as-judge). You describe *what* to check in a declarative
YAML/JSON suite; `llmval` runs it and reports pass/fail.

- **Stdlib-only core** — copy the `llmval/` folder into any project, no install.
- **Works with any language/project** — feed it output inline, from a file, or by
  running a command, so the thing under test (and its LLM) can be anything.
- **Judge via the local `claude` CLI** — no API key. `--no-judge` runs fully offline.
- **Compare against a source of truth** — pull the expected value from a live API
  (or DB, or script) at eval time and match the output against it.
- **CI-ready** — text / JSON / JUnit-XML output and a `--fail-under` exit gate.

Generalized from a QA test-plan governance module (evidence-first judging, honest
"skip" for un-measured dimensions, anti-gaming discipline).

## Contents

- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Suite format](#suite-format)
- [Output & reference sources](#output--reference-sources)
- [Check reference](#check-reference) — every check and its options
- [Comparing against a source-of-truth API](#comparing-against-a-source-of-truth-api)
- [Semantic similarity (embeddings)](#semantic-similarity-embeddings)
- [LLM-as-judge](#llm-as-judge)
- [Sample data](#sample-data)
- [Installation](#installation)
- [CLI reference](#cli-reference)
- [Adding your own check](#adding-your-own-check)
- [Layout](#layout)
- [Scope & caveats](#scope--caveats)

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
     → run each check → status (pass | fail | skip | error) + 0..1 score
     → case passes iff every REQUIRED check passes
suite → all cases pass → exit 0   (or use --fail-under for a pass-rate gate)
```

Four layers, cheapest first. A `skip` (e.g. judge disabled, no embedding backend)
never fails a case — an un-measured check is reported honestly, not passed off as
a pass.

| Layer | Check types | Cost |
|---|---|---|
| Deterministic | `contains` `not_contains` `regex` `equals` `one_of` `min_length` `max_length` `json_valid` `json_schema` `json_path` `no_refusal` `no_pii` | free |
| Lexical similarity | `similarity` (cosine/jaccard) · `keyword_recall` | cheap |
| Semantic similarity | `semantic_similarity` (real embeddings) | model/API |
| LLM-as-judge | `judge` (rubric-based) | CLI call |

**Status meanings:** `pass` / `fail` are self-explanatory; `skip` = not evaluated
(never fails the case); `error` = the check couldn't run (bad config, invalid JSON,
missing reference) and **does** fail the case.

**Case score** = weighted mean of the checks that were actually evaluated
(pass=1, fail=0, scored checks like similarity contribute their measured value).

## Suite format

YAML (needs `pip install pyyaml`) or JSON. Each case needs one **output source**
and a list of **checks**:

```yaml
name: my suite
judge: { backend: cli, cli_path: claude, timeout: 180 }   # or backend: none
defaults: { case_insensitive: true }        # merged into every check (per-check keys win)
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

**Suite keys:** `name`, `judge` (`backend: cli|none`, `cli_path`, `timeout`),
`defaults` (merged into every check), `cases`.

**Per-case keys:** `name`, one output source (below), optional `context` /
`reference` / `prompt` inputs, `checks`, and `timeout` / `shell` for any commands.

**Common check keys (all check types):**
- `type` — required, the check name.
- `weight` — score weighting (default `1.0`).
- `required` — `false` to report but not fail the case (default `true`).

## Output & reference sources

Every text input can come from three places. For the **output** the keys are
`output` / `output_file` / `command` (alias `output_command`); for **context**,
**reference**, and **prompt** they are `<key>` / `<key>_file` / `<key>_command`:

| Source | How | Example |
|---|---|---|
| Inline | `output: "..."` | literal text in the suite |
| File | `output_file: path` | read relative to the suite file |
| Command | `command: "..."` | run it, capture **stdout** (add `shell: true` for pipes) |

- `context` — grounding/source text (used by `judge` faithfulness).
- `reference` — a golden/expected value (used by `equals`, `similarity`,
  `semantic_similarity`, `json_path` `equals_ref`, `judge` correctness).
- `prompt` — the input the model was given (used by `judge` relevance).

Commands run with the working directory set to the **suite file's folder**, and
honor per-case `timeout` (default `120`s) and `shell` (default `false`).

## Check reference

Every check accepts the common keys above (`weight`, `required`). Listed here are
the type-specific options.

### Deterministic (structured & format)

| Check | Options | Passes when |
|---|---|---|
| `contains` | `value` (str or list), `case_insensitive`=true, `mode`=`all`\|`any` | output contains the value(s) |
| `not_contains` | `value` (str or list), `case_insensitive`=true | output contains none of the value(s) |
| `regex` | `pattern`, `case_insensitive`=false, `should_match`=true | regex match state equals `should_match` (DOTALL) |
| `equals` | `value` (literal; **omit to compare to `reference`**), `case_insensitive`=false | trimmed output == value/reference |
| `one_of` | `value` (list), `case_insensitive`=false | trimmed output is one of the options |
| `min_length` | `value`, `unit`=`chars`\|`words` | length ≥ value |
| `max_length` | `value`, `unit`=`chars`\|`words` | length ≤ value |
| `json_valid` | — | output parses as JSON (```json fences tolerated) |
| `json_schema` | `schema` (JSON Schema subset) | output validates against the schema |
| `json_path` | `path` (dotted, e.g. `items.0.id`) + one of: `equals` (literal), `equals_ref` (vs `reference`), `type` (json type), or none (existence) | path resolves and the comparison holds |
| `no_refusal` | — | no "I can't / I'm sorry / as an AI" style refusal found |
| `no_pii` | `kinds` (subset of `email` `phone` `ssn` `credit_card`; default all) | no PII of those kinds detected |

The `json_schema` validator (dependency-free) supports: `type`, `required`,
`properties`, `items`, `enum`, `const`, `additionalProperties` (bool),
`minLength`/`maxLength`, `minimum`/`maximum`, `minItems`/`maxItems`. `true`/`false`
are correctly rejected where an `integer`/`number` is required.

### Similarity (unstructured)

| Check | Options | Passes when |
|---|---|---|
| `similarity` | `reference` (or case `reference`), `method`=`cosine`\|`jaccard`, `min_score`=0.7 | lexical similarity ≥ `min_score` |
| `keyword_recall` | `keywords` (list), `case_insensitive`=true, `min_ratio`=1.0 | fraction of keywords present ≥ `min_ratio` |
| `semantic_similarity` | `reference`, `backend`, `model`, `min_score`=0.75 | embedding cosine ≥ `min_score` (see below) |

### LLM-as-judge

| Check | Options | Passes when |
|---|---|---|
| `judge` | `rubric` (named or free text; default `relevance`), `min_score`=4, plus `context`/`reference`/`prompt` overrides | judge score (1–5) ≥ `min_score` |

## Comparing against a source-of-truth API

To check the LLM output against a value a real API returns, fetch the reference
with `reference_command` (or `context_command`). It runs the command and uses its
stdout — so a `curl` becomes your ground truth:

```yaml
cases:
  # exact match: does the LLM's ETA equal what the orders API says?
  - name: stated ETA matches the API
    output_command: "python3 my_llm_call.py 'when does order 5512 arrive?'"
    reference_command: "curl -s https://api.example.com/orders/5512 | jq -r .eta"
    checks:
      - { type: equals }                       # value omitted -> compare to reference

  # field-level: a field inside the LLM's JSON matches the API value
  - name: extracted eta matches the API
    output_file: out/answer.json
    reference_command: "curl -s https://api.example.com/orders/5512 | jq -r .eta"
    checks:
      - { type: json_path, path: eta, equals_ref: true }
```

The reference works with every reference-aware check, so you pick how strict:

| Comparison | Check |
|---|---|
| Exact string == API value | `equals` (omit `value`) |
| A JSON field == API value | `json_path` + `equals_ref: true` |
| Wording close to API value | `similarity` |
| **Meaning** close to API value | `semantic_similarity` |
| LLM answer consistent with API data (judged) | `judge` with `context_command` |

The same mechanism covers any source of truth — a database query, another
script, a file — anything a command can produce.

Runnable offline demo (uses a local `fake_api.py` in place of `curl`):
`python3 -m llmval run examples/api_comparison_suite.json --no-judge`

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

Backends are auto-detected in order (sentence-transformers, then openai if
`OPENAI_API_KEY` is set); force one with `backend:`. Models are cached across
cases.

## LLM-as-judge

The `judge` check scores subjective quality via the local `claude` CLI (no API
key). It reasons **before** scoring and outputs strict JSON; a score 1–5 is
normalized to 0..1 and compared to `min_score` (default 4).

Named rubrics (or pass free text as `rubric`):

| Rubric | Judges |
|---|---|
| `faithfulness` | every claim grounded in `context` (no hallucination) |
| `relevance` | directly/fully addresses the `prompt` |
| `correctness` | factually correct (vs `reference` if given) |
| `coherence` | well-structured, internally consistent |
| `tone` | appropriate, polite, professional |
| `conciseness` | free of redundancy while complete |
| `safety` | free of harmful/biased/policy-violating content |

Disable per suite with `judge: { backend: none }` or globally with `--no-judge`.
If the CLI is missing or output is unparseable, the check is `skip`, not `fail`.

## Sample data

Runnable out of the box in `examples/` — try these first:

```bash
python3 -m llmval run examples/example_suite.json              --no-judge  # 5 cases, all pass
python3 -m llmval run examples/example_suite.yaml              --no-judge  # inline + file + command sources
python3 -m llmval run examples/sample_suite_with_failures.json --no-judge  # mixed pass/fail — see a real report
python3 -m llmval run examples/api_comparison_suite.json       --no-judge  # match output vs a (fake) API
```

- `example_suite.json` / `.yaml` — one suite showing every output source (inline,
  `output_file`, `command`) and both structured & unstructured checks.
- `sample_suite_with_failures.json` — a small labeled dataset where several cases
  fail on purpose (bad schema type, out-of-set label, PII leak, refusal) so you
  can see how failures render.
- `api_comparison_suite.json` + `fake_api.py` — compare output against a
  source-of-truth value fetched via `reference_command` (offline stand-in for a
  real `curl`).
- `fixtures/` — sample source + summary text used by the RAG/faithfulness case.
- `demo_extractor.py` — a stand-in "LLM call" for the `command:` example; replace
  with your real model call.

## Installation

Zero-install: copy `llmval/` and run `python3 -m llmval`. Or install the CLI:

```bash
pip install -e .                 # gives you the `llmval` command
pip install -e ".[embeddings]"   # + local semantic similarity (sentence-transformers)
pip install -e ".[openai]"       # + OpenAI embeddings backend
pip install -e ".[yaml]"         # + YAML suite support (pyyaml)
```

The core has **no dependencies**; extras only enable optional features.

## CLI reference

```bash
python3 -m llmval run <suite>  [options]
python3 -m llmval checks                 # list all available check types
```

`run` options:

| Option | Effect |
|---|---|
| `--no-judge` | disable the LLM judge (fully offline) |
| `--cli-path PATH` | path to the `claude` CLI (default `claude`) |
| `--format text\|json\|junit` | output format (default `text`) |
| `-o, --output FILE` | write the report to a file instead of stdout |
| `--fail-under N` | exit non-zero if pass rate < N (0..1); default requires all cases to pass |

Exit code: `0` on success, `1` on failure — drops straight into CI.

```bash
python3 -m llmval run suite.yaml --no-judge --format junit -o results.xml
python3 -m llmval run suite.yaml --fail-under 0.9   # allow up to 10% failures
```

## Adding your own check

```python
from llmval.evaluators import evaluator, _res

@evaluator("starts_with")
def _starts_with(check, ctx):
    ok = ctx.output.lstrip().startswith(check["value"])
    return _res(check, ok, f"starts with {check['value']!r}: {ok}")
```

`ctx` exposes `output`, `context`, `reference`, `prompt`, and `judge`. Import your
module before running and the new `type` is usable in any suite. Return `_res(...)`
for pass/fail, or a `CheckResult` with `status="skip"`/`"error"` for the honest
non-evaluated / misconfigured cases.

## Layout

```
llmval/
  core.py            data model (CheckResult / CaseResult / SuiteResult, statuses, EvalContext)
  suite.py           suite loader (YAML/JSON) + JudgeConfig
  evaluators.py      deterministic + lexical-similarity checks, the @evaluator registry
  embeddings.py      semantic_similarity via sentence-transformers / OpenAI (self-registers)
  judge.py           LLM-as-judge via local claude CLI (self-registers)
  jsonschema_mini.py dependency-free JSON Schema subset validator
  runner.py          resolve output/context/reference/prompt → run checks
  report.py          text / json / junit rendering
  cli.py             `run`, `checks`
examples/            runnable JSON + YAML suites, sample data, fake API, demo extractor
tests/               offline unit tests (no CLI/embeddings needed)
```

## Scope & caveats

- `similarity` is **lexical** (token cosine/jaccard) — for meaning, use
  `semantic_similarity` (embeddings) or the `judge`.
- `semantic_similarity` needs an optional backend installed; otherwise it `skip`s.
- The judge is only as reliable as the rubric — calibrate against a few
  human-labeled cases, and prefer a different model to judge than the one tested.
- The bundled JSON Schema validator is a practical subset, not full Draft-7. For
  complex schemas, `pip install jsonschema` and register a custom check.
- Advisory by design: a report is triage signal; wire `--fail-under` into CI when
  you want it to gate a merge.
```
