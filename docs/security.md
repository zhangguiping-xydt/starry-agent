# Security

repo-to-skill is local-first. It uses local scanning, reads the target repository from disk, and does not upload source code.

## Data boundaries

- No remote database is required.
- No vector database is used by default.
- No network service is contacted by the core CLI pipeline.
- Analysis and generation outputs are local files.
- The analyze/generate output must be outside the target repository.

A vector database may become an optional extension later, but it is not an MVP dependency and must not be required for default operation.

## Target repository safety

repo-to-skill does not modify the target repository. Commands that write files require an output/work directory outside the target repository. This prevents generated analysis artifacts or skills from being mixed into application source code.

## Generated helper scripts

Generated repo-reading helper scripts, including repo-map helpers, are read-only. They must keep these boundaries:

- no network
- no dependency installation
- generated helpers do not spawn shell commands
- no writes to the target repository
- no runtime registration

Callable helper scripts can use live HTTP only after explicit endpoint configuration and --execute. Callable helpers default to dry-run/preview mode; live HTTP remains constrained by endpoint and token environment variables plus the explicit `--execute` flag.

The validator checks helper scripts for dangerous operations and validates manifest safety metadata.

## Path and secret hygiene

Generated skill references and `SKILL.md` should not contain machine-specific absolute paths, secrets, tokens, or private evidence locations. Public docs should use relative paths or placeholders.

## Runtime boundary

The open-source project includes an artifact chain, capability evidence, capability graph, skill spec, and verification report. It does not connect to CapabilityRegistry/FastAPI/runtime hot registration, and it is not multi-agent-dev external_skills hot loading.
