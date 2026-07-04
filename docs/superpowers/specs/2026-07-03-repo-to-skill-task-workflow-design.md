# repo-to-skill task-workflow Design

**Status:** Approved (Tasks 1–6 merged on `feat/task-workflow`; Tasks 7–9 pending).
**Date:** 2026-07-03 (backfilled 2026-07-04 from session memory after the file was lost).

## Problem

`repo-to-skill` today produces two output shapes:

- `callable-bundle`: a flat toolkit of independent callable tools.
- `callable-composite`: a linear A→B→C orchestrator over selected interfaces.

Neither fits the case where the user already **knows** the workflow they want — a small, named, predefined read-only sequence (e.g. "count candidates matching a name, then list them"). For that, generating an open-ended orchestrator is the wrong shape: it invites the runtime agent to improvise. The user wants to commit to the workflow at generation time and let the runtime only fill in inputs.

## Goals

1. Add a new `--mode task-workflow` that emits one skill per service, with one or more predefined workflows.
2. Configure the service once at the service level (`<SERVICE>_BASE_URL`, `<SERVICE>_TOKEN`); keep optional per-interface overrides.
3. Default to dry-run; only call the live system when `--execute` is passed and env is configured.
4. v1 supports two read-only patterns: `single-query` (one step) and `count-list-query` (count then list). `lookup-detail` is rejected explicitly.
5. No runtime API orchestration — the workflow is fixed at generation time.

## Non-goals

- No live/runtime composition of workflows from arbitrary interfaces.
- No automatic downgrade to `callable-bundle` when task-workflow cannot be generated — failure is the correct behavior.
- No write-side-effect workflows in v1.

## Architecture

Pipeline extension of the existing loader → planner → renderer → validator → CLI flow:

- **Loader** (`workflow_hints.py`): parses the `--workflow-hints` JSON. Validates `service_env_prefix` (UPPER_SNAKE_CASE), workflow names (safe slugs), patterns (in `{single-query, count-list-query}`), step roles (in `{count, list, detail, lookup}`), and input identifier safety.
- **Planner** (`workflow_planner.py`): consumes `WorkflowHints` + analysis, validates each workflow's shape (`count-list-query` requires steps in order count→list; `single-query` requires exactly one step), resolves each step to a read-safe interface, builds service-level env config.
- **Renderer** (`renderer.py::render_task_workflow`): emits SKILL.md, manifest.yaml (`kind: task-workflow`), one `workflows/<name>.yaml` per workflow, one `scripts/run_<name>.py` runner per workflow, reuses callable-bundle's `tools/<slug>.tool.yaml` and `scripts/call_<slug>.py` for the underlying interfaces.
- **Validator** (`validator.py::_validate_task_workflow`): checks required files, manifest shape (`kind`, service env vars, safety block with `dry_run_default: true` etc., no `side_effects: write` interfaces, workflow files exist on disk), runner hygiene (parses, has `BASE_URL_ENV=`/`TOKEN_ENV=` markers, no hardcoded tokens, defines and respects `--execute`/`--dry-run`).
- **CLI** (`cli.py::_generate_task_workflow`): wires `--mode task-workflow` + `--workflow-hints`; requires `--need`; passes analysis through unchanged (no rewriting of `side_effects`).

## Service configuration model

Single source of truth at the service level:

- `<SERVICE>_BASE_URL` — service root.
- `<SERVICE>_TOKEN` — bearer token.

Optional per-interface overrides (rare):

- `<SLUG>_ENDPOINT` — full URL for that interface; takes precedence over `BASE_URL + route`.
- `<SLUG>_TOKEN` — bearer token for that interface; takes precedence over the service token.

Endpoint resolution in the generated runner: per-interface override → else `BASE_URL.rstrip('/') + route`.

## Safety model

- Runners print the planned request and exit 0 by default.
- `--execute` is required for any live HTTP call.
- Missing `BASE_URL` or `TOKEN` also forces dry-run, even with `--execute`.
- Runners never log tokens; stdout shows `bearer <redacted>` when a token is set, `<SERVICE_TOKEN not set>` when not.
- The validator hard-rejects `manifest.yaml` interfaces with `side_effects: write`.
- The planner hard-rejects any step whose interface is not read-safe (write side-effects, or write-tokens in route/handler names).

## Output layout

```
<skill>/
├── SKILL.md
├── manifest.yaml                      # kind: task-workflow
├── workflows/<name>.yaml              # one per workflow
├── scripts/run_<name>.py              # one runner per workflow
├── scripts/call_<slug>.py             # reused from callable-bundle
├── tools/<slug>.tool.yaml             # reused from callable-bundle
└── references/
    ├── workflow-source.md             # workflow -> step -> interface
    └── service-config.md              # env var reference
```

## Out of scope for v1

- `lookup-detail` pattern (rejected at load with a clear message).
- Write workflows.
- Runtime / dynamic workflow composition.
- Cross-service workflows.
