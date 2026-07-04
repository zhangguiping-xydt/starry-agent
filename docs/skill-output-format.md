# Skill output format

`repo-to-skill generate` converts local analysis artifacts into an AI coding agent skill pack directory. The output is intended to be reviewable before installation.

## Required files

A generated skill contains:

- `manifest.yaml`
- `SKILL.md`
- `scripts/inspect_repo.py`
- `scripts/common.py`
- `references/project-map.md`
- `references/capability-graph.md`
- `references/skill-spec.md`
- `references/confidence-report.md`

## Source artifacts

The skill output is derived from the artifact chain produced by local scanning:

- scan data
- project profile
- capability evidence
- capability graph
- skill spec
- verification report
- confidence report

## task-workflow output

A task-workflow skill is a single skill directory. Top-level files:

- `SKILL.md` — how to configure and run.
- `manifest.yaml` — `kind: task-workflow`, `service` block (`env_prefix`, `base_url_env`, `token_env`), `workflows` list (each with `name`, `pattern`, `file`), `interfaces` list (one entry per underlying interface).
- `workflows/<name>.yaml` — pattern, intent, inputs (cli_name -> wire_name), defaults, steps (role -> slug -> route/method).
- `scripts/run_<name>.py` — dry-run-first runner; prints the planned request unless `--execute` is passed.
- `scripts/call_<slug>.py` and `tools/<slug>.tool.yaml` — one per underlying interface, reused from callable-bundle.
- `references/workflow-source.md` and `references/service-config.md` — provenance and env-var reference.

Generate with `--mode task-workflow`, `--need "<goal>"`, and `--workflow-hints <hints.json>`. Supported v1 patterns are `single-query` and `count-list-query`.

Service-level env: `<SERVICE>_BASE_URL`, `<SERVICE>_TOKEN`. Optional per-interface overrides: `<SLUG>_ENDPOINT`, `<SLUG>_TOKEN`.

## Safety metadata

The manifest records local-first safety boundaries. Generated helper scripts are read-only and must preserve no network, no dependency installation, and generated helpers do not spawn shell commands. They are designed for inspection, not mutation.

## Output placement

repo-to-skill does not modify the target repository. The analyze/generate output must be outside the target repository. Use a sibling work directory, a `.runs` directory outside the input project, or another reviewable local output path.

## Storage and runtime boundary

The output format does not require a remote database and does not use a vector database by default. It also does not register with CapabilityRegistry/FastAPI/runtime hot registration and is not multi-agent-dev external_skills hot loading.

## Adapter boundary

The generated skill pack is the canonical output. Adapter documents can map it into different AI coding agent environments, but adapters must preserve the same local-first safety boundaries and validation requirements.
