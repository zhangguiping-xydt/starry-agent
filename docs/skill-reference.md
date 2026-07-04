# Skill reference

This document is a complete reference for the `repo-to-skill` skill itself — the meta-skill that generates other callable skills. It is intended for users who want to understand exactly what the skill does, when to invoke it, what it produces, and how to read its output.

## What this skill is

`repo-to-skill` is a **meta-skill**: its output is another installable skill. Given a local source repository and a user goal expressed in natural language, it:

1. Statically analyzes the repository.
2. Detects callable HTTP interfaces from source (no API docs required).
3. Scores and selects interfaces that match the goal.
4. Renders a separate, reviewable skill package with tool contracts, safe caller scripts, and source-level provenance.
5. Optionally validates and installs the generated skill.

Use this skill when the user has a legacy or internal codebase with HTTP APIs and wants a focused callable skill for a business goal, not a generic repo map. The goal should require live behavior from the existing system rather than reimplementing the logic.

## When to use

- The user gives you a local repository path and a goal in natural language.
- The repository contains HTTP interfaces (Java/Spring, C#/.NET, Python FastAPI/Flask/Django/Tornado, etc.).
- The user wants to call the live system from another agent, not just read the source.
- The user wants the result as a standalone skill that can be reviewed before installation.

## When not to use

- The repository has no HTTP layer (pure libraries, CLI tools, data pipelines).
- The user only wants a read-only orientation pack (use `--mode repo-map`).
- The user wants to call APIs described by an OpenAPI spec (use a spec-driven tool instead).
- The user wants the tool to invent new APIs — repo-to-skill only surfaces what already exists in source.

## Commands

The skill wraps a single CLI binary, `repo-to-skill`, with these subcommands:

```bash
repo-to-skill analyze <repo> --output <workdir>/analysis
repo-to-skill generate <repo> \
  --analysis <workdir>/analysis \
  --output <workdir>/skill \
  --mode callable-bundle | callable-composite | task-workflow | repo-map \
  --goal "<user goal>"            # required for callable-composite
  --need "<user goal>"            # used by callable-bundle fallback; required for task-workflow
  --workflow-hints <hints.json>   # required for task-workflow
  --selected-slugs slug-a,slug-b  # optional agent override
  --selection-json <path>         # optional full selection file
  --max-interfaces 12             # bundle default; composite default 5
  --language auto | zh-CN | en
repo-to-skill validate <workdir>/skill/<slug>
repo-to-skill compose <repo> --output <workdir> --mode <m> --goal <g>   # analyze + generate + validate in one go
repo-to-skill eval --case <case-name>                                    # deterministic regression
repo-to-skill doctor                                                     # local runtime readiness check
```

### Modes

| Mode | Output | Best for |
|------|--------|----------|
| `repo-map` | Orientation pack (no live calls) | Exploration, onboarding, "what does this repo do?" |
| `callable-bundle` | Bundle of independent callable tools | "Give me a toolkit for X" — each tool is a standalone API |
| `callable-composite` | Linear A→B→C orchestrator + bundle | "Compute a final answer that requires calling several APIs in order" |
| `task-workflow` | One skill per predefined workflow over a service | "Run a known read-only count-then-list flow against this service, do not improvise API chains" |

## Generated skill shape

### repo-map

```text
<repo-slug>/
├── manifest.yaml
├── SKILL.md
├── scripts/inspect_repo.py
├── scripts/common.py
└── references/
    ├── project-map.md
    ├── capability-graph.md
    ├── skill-spec.md
    └── confidence-report.md
```

### callable-bundle

```text
<bundle-slug>/
├── manifest.yaml                      # kind: callable-bundle, selection, safety
├── SKILL.md                           # when to use, what tools it contains
├── tools/
│   ├── <api-a>.tool.yaml              # machine-readable tool contract
│   └── <api-b>.tool.yaml
├── scripts/
│   ├── call_<api-a>.py                # safe caller, preview by default
│   └── call_<api-b>.py
└── references/
    ├── capability-selection.md        # why each API was selected
    └── capability-source.md           # route, handler, business method, fields
```

### callable-composite

```text
<composite-slug>/
├── manifest.yaml                      # kind: callable-composite, composition.goal/steps
├── SKILL.md                           # composite instructions for the generating agent
├── orchestrator.py                    # fixed-order chain with TODO field-mapping markers
├── tools/<api-a>.tool.yaml
├── tools/<api-b>.tool.yaml
├── scripts/call_<api-a>.py
├── scripts/call_<api-b>.py
└── references/
    ├── composition.md                 # ordered steps + required field mappings
    └── capability-source.md           # per-API source provenance
```

### task-workflow

A task-workflow skill is generated when the goal maps to a **predefined** workflow (declared up-front in a hints JSON file) rather than an ad-hoc API chain. The renderer emits:

```text
<skill>/
├── SKILL.md                           # how to run the workflow
├── manifest.yaml                      # kind: task-workflow, service, workflows, interfaces
├── workflows/<name>.yaml              # one file per workflow (pattern, steps, inputs, defaults)
├── scripts/run_<name>.py              # dry-run-first runner per workflow
├── scripts/call_<slug>.py             # one caller per underlying interface (reused from callable)
├── tools/<slug>.tool.yaml             # one tool contract per interface (reused from callable)
└── references/
    ├── workflow-source.md             # workflow -> step -> interface mapping
    └── service-config.md              # service-level env vars + per-interface overrides
```

Configure once per service with `<SERVICE>_BASE_URL` and `<SERVICE>_TOKEN`. Per-interface overrides via `<SLUG>_ENDPOINT` / `<SLUG>_TOKEN` are optional. Every runner prints the planned request and sends nothing unless `--execute` is passed.

Supported v1 patterns: `single-query` (one read-only step) and `count-list-query` (count then list, both read-only). `lookup-detail` is **not supported** in v1.

## Data model

The analysis pipeline is built on a small explicit data model (defined in `repo_to_skill/models.py`). The most important structures:

### IoField

A single input or output field of an HTTP interface.

| Property | Description |
|----------|-------------|
| `name` | Field name as it appears on the wire. |
| `type` | JSON schema type (`string`, `number`, `integer`, `boolean`, `array`, `object`, `unknown`). |
| `required` | Whether the field is required in the request. |
| `description` | Description if present in source; otherwise empty. |
| `source_path` | File where the field was declared. |
| `source_symbol` | Type/class/record that declared the field. |
| `confidence` | Static-analysis confidence (0.0–1.0). |
| `location` | `body`, `path`, or `query`. |

### CallableInterface

A single detected HTTP endpoint.

| Property | Description |
|----------|-------------|
| `id` | Stable hash-derived identifier. |
| `slug` | Human-readable identifier used in `--selected-slugs`. |
| `stack` | `java`, `csharp`, `python`, etc. |
| `framework` | `spring`, `aspnet`, `fastapi`, `flask`, etc. |
| `transport` | Always `http` in MVP. |
| `http_method` | `GET`, `POST`, etc. |
| `route` | URL path template. |
| `handler_symbol` | Function or method name in source. |
| `handler_path` / `handler_line` | Source location. |
| `business_method` | Named service method the handler calls, if any. |
| `request` / `response` | `IoContract` instances. |
| `endpoint_env` | Environment variable name the caller reads for the base URL. |
| `token_env` | Environment variable name the caller reads for the auth token. |
| `auth_required` | Whether the caller should send a token. |
| `side_effects` | `none`, `read`, `write`, `unknown`. |
| `confidence` | Static-analysis confidence. |
| `evidence` | List of evidence pointers backing the detection. |

## Selection algorithm

Selection is implemented in `repo_to_skill/skillgen/callable_selector.py` and runs in two modes:

### Agent-driven (`--selected-slugs` or `--selection-json`)

The generating agent provides explicit slugs. The tool validates each slug exists in `callable_capabilities.json`, assigns each a score of `1.0` with reason `"selected by agent slug"`, and records `selection_source: agentic`. Unknown slugs raise `unknown callable interface slug: <slug>` — this is fail-loud by design.

### Deterministic fallback (`--need` or `--goal` only)

A TF-IDF-style scorer ranks every detected interface against the goal text:

1. Tokenize the goal (alphanumeric tokens, stopwords removed).
2. For each interface, tokenize each metadata field (`slug`, `handler_symbol`, `route`, `business_method`, `request_fields`, `request_model`, `response_fields`, `response_model`, `framework`, `stack`, `side_effects`).
3. Compute IDF across the entire interface catalog so rare business terms dominate over common tokens.
4. For each field, sum `(1 + TF) * IDF` for every goal token that matches, then multiply by the field weight (see [How it works](how-it-works.md#deterministic-scorer)).
5. Take the top-N (default 12 for bundle, 5 for composite).

The selection is logged with `selection_source: deterministic` and each item carries `score` and `reasons` (the matched fields and tokens).

## Orchestrator and composition

When the mode is `callable-composite`, the renderer emits `orchestrator.py` plus `references/composition.md`. The orchestrator:

- Imports each caller script via `importlib.util.spec_from_file_location`.
- Calls them in fixed order: `step_0` → `step_1` → … → `step_N`.
- For each step after `step_0`, includes `# TODO: fill from step_<n>.<field>` markers in the CLI argument construction. The generating agent replaces these markers with concrete code that passes the right response field from step N-1 into step N's request.
- Defaults to **preview mode**. It only forwards `--execute` to the callers when the user passes `--execute` and every step's endpoint environment variable is set. If any endpoint env is unset, the orchestrator stays in preview regardless of `--execute`.

The validator enforces that the orchestrator contains at least one `# TODO: fill from step_` marker. This is a deliberate fail-loud signal: a composite without any TODO has either been completed (good) or was rendered incorrectly (bad). The generating agent removes the TODOs as it fills in the mappings; the validator is a safety net, not the primary correctness check.

## Safety model

Every generated skill follows the same safety boundary:

- **Preview by default.** Callers print the request they would send and return a placeholder response. Live HTTP requires the endpoint environment variable to be set and `--execute` to be passed.
- **No hard-coded endpoints or tokens.** Endpoints and tokens come from environment variables named in the manifest. Names are derived from the API slug, not from real infrastructure.
- **No dangerous primitives.** The validator bans `subprocess`, bare `open()`, writable open modes. Only `urllib.request` / `urllib.error` are allowed for network access.
- **No machine-path leakage.** The generated skill must not contain `/home/`, `/tmp/`, `/media/`, absolute paths, internal URLs, or credentials. The validator scans every file in the generated skill.
- **Non-invasive to the target.** Analysis and generation output must live outside the target repository. The tool refuses to write inside the input path.

## Workflow the generating agent follows

When invoked, the `repo-to-skill` skill runs this workflow:

1. **Analyze.** Run `repo-to-skill analyze <repo> --output <workdir>/analysis`. Do not modify the target repository.
2. **Inspect the callable catalog.** Read `<workdir>/analysis/callable_capabilities.json`. Focus on each interface's `slug`, `route`, `handler_symbol`, `business_method`, request/response fields, and safety notes.
3. **Translate the goal into slugs.** Pick 3–20 interfaces for `callable-bundle`, or 2–5 for `callable-composite`. Prefer fewer when the goal is narrow. Never invent slugs — every slug must appear in the catalog.
4. **Write a selection file** (optional but recommended):
   ```json
   {
     "need_summary": "Generate a callable skill for <concrete goal>.",
     "selected_slugs": ["first-slug", "second-slug"],
     "selection_source": "agentic"
   }
   ```
5. **Generate.** Run `repo-to-skill generate` with `--mode`, `--goal`, and either `--selected-slugs` or `--selection-json`.
6. **Validate.** Run `repo-to-skill validate <workdir>/skill/<slug>`. Fix any findings before installing.
7. **For composites only: fill the TODO markers.** Read `references/composition.md`, decide which response fields from step N-1 must flow into step N's request, and replace every `# TODO: fill from step_<n>.<field>` in `orchestrator.py` with concrete code. Re-validate after editing.
8. **Install (optional).** Pass `--install` on `generate`, or copy the skill directory into `~/.claude/skills` / `~/.agents/skills` manually.

## How to read the output

- **`manifest.yaml`** — start here. The `kind` tells you what the skill does; `safety` records the boundaries; `selection` records why each API was picked.
- **`SKILL.md`** — read this to know when to invoke the skill from another agent.
- **`references/capability-source.md`** — the audit trail. Every API maps back to a route, handler, business method, and typed fields with source locations.
- **`references/capability-selection.md`** (bundle) or **`references/composition.md`** (composite) — why these APIs, in this order, for this goal.
- **`tools/*.tool.yaml`** — the machine-readable contract. Each tool declares its CLI arguments, endpoint env, token env, and JSON schema.
- **`scripts/call_*.py`** — the safe caller. Read it before installing to confirm it does what the contract claims.
- **`orchestrator.py`** (composite only) — the chain. Look for `# TODO: fill from step_` markers; if any remain, the composite is not ready for end users.

## Install locations

- `~/.claude/skills/<skill-name>/` — for Claude Code and Claude-compatible agents.
- `~/.agents/skills/<skill-name>/` — for OpenCode-style agents.
- `~/.icodemate/cli/skills/<skill-name>/` — for co-mind (iCodeMate).

The skill is a directory of files. Installation does not run any setup script, register with a capability service, or modify agent configuration beyond placing the directory in the right location.

## Limitations

- **No source-level data-flow tracing.** Composite field mappings are TODO markers, not auto-resolved bindings.
- **No runtime capture.** If a behavior only exists in a running system (e.g., dynamic dispatch, plugin-loaded handlers), static analysis will not find it.
- **No LLM in the tool loop.** All analysis, selection, generation, and validation are deterministic. Judgment work is delegated to the generating agent at slug-selection and composite-mapping time.
- **HTTP-only in MVP.** gRPC, GraphQL, and message-queue consumers are not detected.
- **Multi-stack but not universal.** Detection covers Java/Spring, C#/.NET, and Python HTTP frameworks. Other stacks will produce a `repo-map` but may miss callable interfaces.

## Related documents

- [How it works](how-it-works.md) — the pipeline design and stage-by-stage reasoning.
- [Architecture](architecture.md) — internal module layout and artifact flow.
- [Skill output format](skill-output-format.md) — required files and manifest fields per skill kind.
- [Security](security.md) — safety boundary details.
- [Evals](evals.md) — deterministic regression coverage.
