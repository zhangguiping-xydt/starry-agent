# repo-to-skill task-workflow Implementation Plan (Tasks 7–9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the task-workflow generator so it supports the `single-query` workflow pattern, explicitly rejects `lookup-detail`, documents the new mode end-to-end, and passes a full regression sweep.

**Architecture:** `repo-to-skill` is a Python 3.11 meta-skill generator with a loader → planner → renderer → validator → CLI pipeline. Tasks 1–6 added the `task-workflow` mode for the `count-list-query` pattern, service-level env config, dry-run-by-default runners, and a CLI flag. The `single-query` pattern (one step, one read-only call) is accepted by the loader today but produces a `NotImplementedError` runner and is never planned. `lookup-detail` is silently accepted by the loader today but should be rejected explicitly because v1 supports only read-only patterns. Tasks 7–9 close those gaps.

**Tech Stack:** Python ≥3.11, typer (CLI), jinja2 (templates), pyyaml (manifest parsing), pytest + ruff (testing/lint).

**Status entering Task 7:** Branch `feat/task-workflow` has 13 commits implementing Tasks 1–6. The 8 tests that today use `pattern: "single-query"` (in `tests/test_workflow_planner.py` and `tests/test_workflow_renderer.py`) are exercising only loader-level behavior or are expected to fail once `single-query` is fully implemented; Task 7 will both make single-query work and update those tests where needed.

**Reference points (existing code):**
- Loader: `repo_to_skill/skillgen/workflow_hints.py` — currently accepts `{single-query, count-list-query, lookup-detail}`.
- Planner: `repo_to_skill/skillgen/workflow_planner.py::_build_workflow` — validates `count-list-query` step order, raises for write interfaces.
- Renderer: `repo_to_skill/skillgen/renderer.py::render_task_workflow` + templates under `repo_to_skill/skillgen/templates/task_workflow/`.
- Runner template: `repo_to_skill/skillgen/templates/task_workflow/scripts/run_workflow.py.j2` — has a `count-list-query` branch and an `{% else %}` that raises `NotImplementedError`.
- Validator: `repo_to_skill/skillgen/validator.py::_validate_task_workflow`.
- CLI: `repo_to_skill/cli.py::_generate_task_workflow` and the `generate` command.

---

## Task 7: support single-query, reject lookup-detail

**Goal of this task:** `single-query` becomes a fully functional one-step workflow; `lookup-detail` is rejected at load time with a clear message.

**Files:**
- Modify: `repo_to_skill/skillgen/workflow_hints.py` (reject `lookup-detail` at load)
- Modify: `repo_to_skill/skillgen/workflow_planner.py` (validate `single-query` shape: exactly one step, role in `{lookup, detail, count, list}`)
- Modify: `repo_to_skill/skillgen/templates/task_workflow/scripts/run_workflow.py.j2` (add `single-query` branch in the runner)
- Test: `tests/test_workflow_planner.py` (loader rejection + planner validation)
- Test: `tests/test_workflow_renderer.py` (single-query render + dry-run + execute seam)

### Step 1: write failing tests for `lookup-detail` rejection

Append to `tests/test_workflow_planner.py`:

```python
def test_load_workflow_hints_rejects_lookup_detail_pattern(tmp_path: Path) -> None:
    path = _write_hints(
        tmp_path,
        {
            "service_env_prefix": "EXAMPLE_SERVICE",
            "workflows": [
                {
                    "name": "lookup_record",
                    "pattern": "lookup-detail",
                    "steps": {"lookup": "example-query"},
                    "inputs": {"keyword": "nameConcat"},
                }
            ],
        },
    )

    with pytest.raises(ValueError) as exc:
        load_workflow_hints(path)

    message = str(exc.value)
    assert "lookup-detail" in message
    assert "not supported" in message.lower()
```

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_planner.py::test_load_workflow_hints_rejects_lookup_detail_pattern -v`
Expected: FAIL — loader currently accepts `lookup-detail`, so no exception is raised.

### Step 2: make loader reject `lookup-detail`

In `repo_to_skill/skillgen/workflow_hints.py`, change the pattern validation block. Find:

```python
        _require(
            pattern in {"single-query", "count-list-query", "lookup-detail"},
            f"{workflow_path} unsupported workflow pattern: {pattern}",
        )
```

Replace with:

```python
        _require(
            pattern in {"single-query", "count-list-query"},
            f"{workflow_path} unsupported workflow pattern: {pattern} "
            "(lookup-detail is not supported in v1)",
        )
```

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_planner.py -v`
Expected: PASS, including the new `lookup-detail` rejection test. The 8 existing `single-query` tests still pass (loader still accepts `single-query`).

### Step 3: write failing tests for `single-query` planner validation

Append to `tests/test_workflow_planner.py` (the existing `_prepare`/`_hints` helpers there already build a synthetic analysis):

```python
def test_plan_task_workflow_supports_single_query(tmp_path: Path) -> None:
    repo, analysis = _prepare_single_query(tmp_path)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="find_record",
                pattern="single-query",
                steps=(WorkflowHintStep(role="lookup", slug="example-query"),),
                inputs={"keyword": "nameConcat"},
                defaults={"pageSize": 20},
            ),
        ),
    )

    plan = plan_task_workflow(
        repo, analysis, hints=hints, need_summary="find one record", language="en"
    )

    assert len(plan.workflows) == 1
    workflow = plan.workflows[0]
    assert workflow.pattern == "single-query"
    assert [step.role for step in workflow.steps] == ["lookup"]
    assert workflow.steps[0].slug == "example-query"


def test_plan_task_workflow_single_query_rejects_two_steps(tmp_path: Path) -> None:
    repo, analysis = _prepare_single_query(tmp_path)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="find_record",
                pattern="single-query",
                steps=(
                    WorkflowHintStep(role="lookup", slug="example-query"),
                    WorkflowHintStep(role="detail", slug="example-query"),
                ),
                inputs={"keyword": "nameConcat"},
                defaults={},
            ),
        ),
    )

    with pytest.raises(ValueError) as exc:
        plan_task_workflow(
            repo, analysis, hints=hints, need_summary="x", language="en"
        )

    assert "find_record" in str(exc.value)
    assert "single-query" in str(exc.value)
```

Append the helper `_prepare_single_query` near the existing `_prepare` helper in the same file. The function must build a synthetic analysis directory with one read-safe interface:

```python
def _prepare_single_query(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interface = {
        "slug": "example-query",
        "stack": "java",
        "framework": "spring",
        "http_method": "POST",
        "route": "/example/query",
        "handler_symbol": "Controller.example_query",
        "handler_path": "src/main/java/example/Controller.java",
        "business_method": "Service.example_query",
        "endpoint_env": "EXAMPLE_QUERY_ENDPOINT",
        "token_env": "EXAMPLE_QUERY_TOKEN",
        "side_effects": "read",
        "request": {
            "model_name": "ExampleQueryRequest",
            "fields": [{"name": "nameConcat", "type": "string", "required": False}],
            "unresolved": False,
            "notes": [],
        },
        "response": {
            "model_name": "ExampleQueryResponse",
            "fields": [],
            "unresolved": False,
            "notes": [],
        },
    }
    (analysis / "scan.json").write_text(
        json.dumps({"root": str(repo), "files": []}), encoding="utf-8"
    )
    (analysis / "profile.json").write_text(
        json.dumps({"name": "example-service"}), encoding="utf-8"
    )
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "example-service", "interfaces": [interface], "notes": []}),
        encoding="utf-8",
    )
    return repo, analysis
```

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_planner.py::test_plan_task_workflow_supports_single_query tests/test_workflow_planner.py::test_plan_task_workflow_single_query_rejects_two_steps -v`
Expected: FAIL — `_build_workflow` has no single-query branch; the success case will fall through, and the two-step case will not raise the expected error.

### Step 4: implement `single-query` planner validation

In `repo_to_skill/skillgen/workflow_planner.py::_build_workflow`, after the existing `count-list-query` block and before the step resolution loop, add:

```python
    if hint.pattern == "single-query" and len(hint.steps) != 1:
        raise ValueError(
            f"workflow '{hint.name}': single-query requires exactly one step"
        )
```

No other planner change is needed — the existing step-resolution loop already handles a single step.

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_planner.py -v`
Expected: PASS, all planner tests green.

### Step 5: write failing renderer test for `single-query`

Append to `tests/test_workflow_renderer.py`:

```python
def test_render_task_workflow_single_query_runner_dry_run(tmp_path: Path) -> None:
    repo, analysis = _prepare_single(tmp_path)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="find_record",
                pattern="single-query",
                steps=(WorkflowHintStep(role="lookup", slug="example-query"),),
                inputs={"keyword": "nameConcat"},
                defaults={"pageSize": 20},
            ),
        ),
    )
    plan = plan_task_workflow(
        repo, analysis, hints=hints, need_summary="按关键词查一条", language="zh-CN"
    )

    skill = render_task_workflow(plan, tmp_path / "skill")

    runner_path = skill / "scripts" / "run_find_record.py"
    assert runner_path.is_file()

    spec = importlib.util.spec_from_file_location("task_workflow_runner_single", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _no_call(*_args, **_kwargs):
        raise AssertionError("runner must not send a request in dry-run mode")

    monkeypatch_like = _NoCallPatcher()
    monkeypatch_like.patch(module, "_send_request", _no_call)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--keyword", "Alice"])

    assert rc == 0
    out = buffer.getvalue()
    assert "[dry-run]" in out
    assert "find_record" in out
    assert "secret" not in out


class _NoCallPatcher:
    """Tiny shim to patch a module attribute without pulling pytest into the runner."""

    def __init__(self) -> None:
        self._original: dict[str, object] = {}

    def patch(self, module: object, name: str, value: object) -> None:
        self._original[name] = getattr(module, name)
        setattr(module, name, value)
```

(`_prepare_single` already exists in `tests/test_workflow_renderer.py` — reuse it; the renderer test file currently uses synthetic read-safe interfaces, so a single-interface variant fits.)

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_renderer.py::test_render_task_workflow_single_query_runner_dry_run -v`
Expected: FAIL — the runner template's `{% else %}` branch raises `NotImplementedError` for `single-query`.

### Step 6: add `single-query` branch to the runner template

Edit `repo_to_skill/skillgen/templates/task_workflow/scripts/run_workflow.py.j2`. Find the existing block:

```jinja
{% if workflow.pattern == "count-list-query" %}
def main(argv: list[str]) -> int:
    ...existing count-list-query body...
    return 0
{% else %}
def main(argv: list[str]) -> int:
    raise NotImplementedError(
        "runner for pattern {{ workflow.pattern }} is not implemented yet"
    )
{% endif %}
```

Replace the `{% else %}` with an `elif single-query` branch and a final `else`. The new single-query branch should: build the payload from DEFAULTS + CLI overrides, resolve the single step endpoint/token, dry-run by default, and on `--execute` send one request through `_send_request`. Use this exact body (it parallels the count branch):

```jinja
{% if workflow.pattern == "count-list-query" %}
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the {{ workflow.name }} workflow.")
{% for input in workflow.inputs %}
    parser.add_argument("--{{ input.name }}", help="{{ input.name }} -> {{ input.maps_to }}")
{% endfor %}
    parser.add_argument("--execute", action="store_true", help="Send live HTTP calls.")
    parser.add_argument("--dry-run", action="store_true", help="Force preview (default).")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    payload: dict = dict(DEFAULTS)
{% for input in workflow.inputs %}
    value = getattr(args, "{{ input.name | replace('-', '_') }}", None)
    if value is not None:
        payload["{{ input.maps_to }}"] = value
{% endfor %}

    count_endpoint = _endpoint(STEP_COUNT_ROUTE, STEP_COUNT_ENDPOINT_ENV)
    list_endpoint = _endpoint(STEP_LIST_ROUTE, STEP_LIST_ENDPOINT_ENV)
    token = _token(STEP_COUNT_TOKEN_ENV)

    dry_run = args.dry_run or not args.execute or not count_endpoint or not list_endpoint
    if dry_run:
        print("[dry-run] {{ workflow.name }} not sending any request.")
        print("  count endpoint: " + (count_endpoint or "<" + BASE_URL_ENV + ">"))
        print("  list endpoint:  " + (list_endpoint or "<" + BASE_URL_ENV + ">"))
        print("  auth:           " + ("bearer <redacted>" if token else "<" + TOKEN_ENV + " not set>"))
        print("  payload:        " + json.dumps(payload, ensure_ascii=False))
        return 0

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token

    count_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    count_request = urllib.request.Request(
        count_endpoint, data=count_body, method=STEP_COUNT_METHOD, headers=headers
    )
    try:
        raw_count = _send_request(count_request, args.timeout)
    except urllib.error.URLError as error:
        print("[error] count step failed: " + str(error))
        return 1

    try:
        count_doc = json.loads(raw_count)
    except json.JSONDecodeError:
        print("[error] count step returned non-JSON")
        return 1

    total = count_doc.get("bo") if isinstance(count_doc, dict) else None
    print("[count] total: " + json.dumps(count_doc, ensure_ascii=False, indent=2))
    if not total:
        print("[list] skipped: count is zero or missing")
        return 0

    list_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    list_request = urllib.request.Request(
        list_endpoint, data=list_body, method=STEP_LIST_METHOD, headers=headers
    )
    try:
        raw_list = _send_request(list_request, args.timeout)
    except urllib.error.URLError as error:
        print("[error] list step failed: " + str(error))
        return 1

    try:
        list_doc = json.loads(raw_list)
    except json.JSONDecodeError:
        print(raw_list)
        return 0

    print("[list] rows: " + json.dumps(list_doc, ensure_ascii=False, indent=2))
    return 0
{% elif workflow.pattern == "single-query" %}
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the {{ workflow.name }} workflow.")
{% for input in workflow.inputs %}
    parser.add_argument("--{{ input.name }}", help="{{ input.name }} -> {{ input.maps_to }}")
{% endfor %}
    parser.add_argument("--execute", action="store_true", help="Send live HTTP calls.")
    parser.add_argument("--dry-run", action="store_true", help="Force preview (default).")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    payload: dict = dict(DEFAULTS)
{% for input in workflow.inputs %}
    value = getattr(args, "{{ input.name | replace('-', '_') }}", None)
    if value is not None:
        payload["{{ input.maps_to }}"] = value
{% endfor %}

    step_route = STEP_{{ workflow.steps[0].role | upper }}_ROUTE
    step_method = STEP_{{ workflow.steps[0].role | upper }}_METHOD
    step_endpoint_env = STEP_{{ workflow.steps[0].role | upper }}_ENDPOINT_ENV
    step_token_env = STEP_{{ workflow.steps[0].role | upper }}_TOKEN_ENV

    endpoint = _endpoint(step_route, step_endpoint_env)
    token = _token(step_token_env)

    dry_run = args.dry_run or not args.execute or not endpoint
    if dry_run:
        print("[dry-run] {{ workflow.name }} not sending any request.")
        print("  endpoint: " + (endpoint or "<" + BASE_URL_ENV + ">"))
        print("  auth:     " + ("bearer <redacted>" if token else "<" + TOKEN_ENV + " not set>"))
        print("  payload:  " + json.dumps(payload, ensure_ascii=False))
        return 0

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, method=step_method, headers=headers
    )
    try:
        raw = _send_request(request, args.timeout)
    except urllib.error.URLError as error:
        print("[error] single-query step failed: " + str(error))
        return 1

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return 0

    print("[single-query] " + json.dumps(doc, ensure_ascii=False, indent=2))
    return 0
{% else %}
def main(argv: list[str]) -> int:
    raise NotImplementedError(
        "runner for pattern {{ workflow.pattern }} is not implemented yet"
    )
{% endif %}
```

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_renderer.py -v`
Expected: PASS for the new single-query test; existing renderer tests still green.

### Step 7: tighten validator to recognize both supported patterns

The validator's runner check (`_check_task_workflow_runners`) already verifies `args.dry_run`/`args.execute` and the safety markers. No validator change is needed for Task 7. (Single-query runners emit the same markers.) Sanity-run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_workflow_validator.py -v` — should remain all green.

### Step 8: full sweep + ruff

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest -q`
Expected: all green (172 prior tests + new ones).

Run: `cd /media/vdc/code/repo-to-skill && python -m ruff check repo_to_skill tests`
Expected: `All checks passed!`

### Step 9: commit

```bash
cd /media/vdc/code/repo-to-skill
git add repo_to_skill/skillgen/workflow_hints.py \
        repo_to_skill/skillgen/workflow_planner.py \
        repo_to_skill/skillgen/templates/task_workflow/scripts/run_workflow.py.j2 \
        tests/test_workflow_planner.py \
        tests/test_workflow_renderer.py
git commit -m "feat(skillgen): support single-query workflows, reject lookup-detail"
```

---

## Task 8: documentation for task-workflow

**Goal of this task:** Make `--mode task-workflow` discoverable and documented in every user-facing surface (the repo-to-skill skill reference in both English and Chinese, the output format reference, and the repo-to-skill SKILL body), and add a test guard so the docs cannot drift.

**Files:**
- Modify: `docs/skill-reference.md`
- Modify: `docs/skill-reference.zh-CN.md`
- Modify: `docs/skill-output-format.md`
- Modify: `repo_to_skill/skills/repo-to-skill/SKILL.md` (the skill body — adjust path if the installer layout puts it elsewhere; check via `find repo_to_skill -name 'SKILL.md'`)
- Modify: `tests/test_docs.py`

### Step 1: locate the skill body file

Run: `cd /media/vdc/code/repo-to-skill && find . -name 'SKILL.md' -not -path './.git/*'`
This lists the SKILL body file(s). The repo-to-skill skill lives at `~/.claude/skills/repo-to-skill/SKILL.md` once installed, but the source-of-truth copy inside the repo is the file to update here.

### Step 2: add `task-workflow` to `docs/skill-reference.md`

In the mode table (around lines 55–60) and the command block (around lines 38–45), add `task-workflow` alongside `callable-bundle` and `callable-composite`. Concretely:

In the command block:
```markdown
repo-to-skill generate <repo> \
  --mode callable-bundle | callable-composite | task-workflow | repo-map \
  --analysis <workdir>/analysis \
  --output <workdir>/skill \
  --goal "<user goal>"            # required for callable-composite
  --need "<user goal>"            # used by callable-bundle fallback; required for task-workflow
  --workflow-hints <hints.json>   # required for task-workflow
  --language auto | zh-CN | en
```

In the mode table, add a row:
```markdown
| `task-workflow` | One skill per predefined workflow over a service | "Run a known read-only count-then-list flow against this service, do not improvise API chains" |
```

Add a new `### task-workflow` subsection after the `### callable-composite` subsection (around line 110), with this content:

```markdown
### task-workflow

A task-workflow skill is generated when the goal maps to a **predefined** workflow (declared up-front in a hints JSON file) rather than an ad-hoc API chain. The renderer emits:

```
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
```

### Step 3: mirror the changes in `docs/skill-reference.zh-CN.md`

Apply the same edits to the Chinese reference (command block, mode table, new `### task-workflow` subsection) in Chinese. Match the style of the existing `### callable-composite` Chinese subsection.

### Step 4: document `task-workflow` output in `docs/skill-output-format.md`

Add a section titled `## task-workflow output` near the existing `## callable-bundle output` / `## callable-composite output` sections. Content mirrors the layout above, briefly:

```markdown
## task-workflow output

A task-workflow skill is a single skill directory. Top-level files:

- `SKILL.md` — how to configure and run.
- `manifest.yaml` — `kind: task-workflow`, `service` block (`env_prefix`, `base_url_env`, `token_env`), `workflows` list (each with `name`, `pattern`, `file`), `interfaces` list (one entry per underlying interface).
- `workflows/<name>.yaml` — pattern, intent, inputs (cli_name -> wire_name), defaults, steps (role -> slug -> route/method).
- `scripts/run_<name>.py` — dry-run-first runner; prints the planned request unless `--execute` is passed.
- `scripts/call_<slug>.py` and `tools/<slug>.tool.yaml` — one per underlying interface, reused from callable-bundle.
- `references/workflow-source.md` and `references/service-config.md` — provenance and env-var reference.

Service-level env: `<SERVICE>_BASE_URL`, `<SERVICE>_TOKEN`. Optional per-interface overrides: `<SLUG>_ENDPOINT`, `<SLUG>_TOKEN`.
```

### Step 5: update the repo-to-skill SKILL body

Open the file from Step 1 and add a short subsection for task-workflow alongside any existing `callable-bundle` / `callable-composite` descriptions. Keep it short — point to the docs/ files for detail:

```markdown
## Mode: task-workflow

Use when the goal maps to a **predefined** workflow (count-then-list, single read-only query) rather than an ad-hoc API chain. Provide `--workflow-hints <hints.json>` and `--need "<goal>"`. v1 supports `single-query` and `count-list-query` only. See `docs/skill-reference.md` for the hints schema and the generated layout.
```

### Step 6: add a docs guard test

Append to `tests/test_docs.py` a new test that requires the public docs to mention `task-workflow`:

```python
def test_public_docs_mention_task_workflow_mode() -> None:
    targets = [
        REPO_ROOT / "docs" / "skill-reference.md",
        REPO_ROOT / "docs" / "skill-reference.zh-CN.md",
        REPO_ROOT / "docs" / "skill-output-format.md",
    ]
    for path in targets:
        assert path.is_file(), f"missing document: {path.name}"
        text = path.read_text(encoding="utf-8")
        assert "task-workflow" in text, f"{path.name} must mention task-workflow mode"
        assert "--workflow-hints" in text, f"{path.name} must mention --workflow-hints"
        assert "single-query" in text, f"{path.name} must mention single-query pattern"
        assert "count-list-query" in text, f"{path.name} must mention count-list-query pattern"
```

### Step 7: run tests + ruff + commit

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest tests/test_docs.py -v`
Expected: PASS.

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest -q && python -m ruff check repo_to_skill tests`
Expected: all green.

```bash
cd /media/vdc/code/repo-to-skill
git add docs/skill-reference.md docs/skill-reference.zh-CN.md docs/skill-output-format.md \
        repo_to_skill/skills/repo-to-skill/SKILL.md tests/test_docs.py
git commit -m "docs: document --mode task-workflow and workflow hints schema"
```

(Adjust the `git add` path for the SKILL body if Step 1 found it elsewhere.)

---

## Task 9: full regression sweep

**Goal of this task:** Confirm the whole feature works end-to-end on the example repo and that nothing in the broader codebase regressed. Produce a clean final state ready for `superpowers:finishing-a-development-branch`.

**Files:**
- No source changes expected. If a regression surfaces, fix it in a follow-up commit before finishing.

### Step 1: full test + lint sweep

Run: `cd /media/vdc/code/repo-to-skill && python -m pytest -q`
Expected: all green (172 + new single-query + lookup-detail tests).

Run: `cd /media/vdc/code/repo-to-skill && python -m ruff check repo_to_skill tests`
Expected: `All checks passed!`

### Step 2: end-to-end smoke test on the HRM sample repo

The HRM repo at `/media/vdc/code/job/zte-hrm-job-service` is the regression sample. Run analyze → generate a `count-list-query` task-workflow skill → validate. Use a tmp workdir:

```bash
WORKDIR="$(mktemp -d)"
HINTS="$WORKDIR/hints.json"
cat > "$HINTS" <<'JSON'
{
  "service_env_prefix": "ZTE_HRM_ONBOARDING",
  "workflows": [
    {
      "name": "query_resume_records",
      "pattern": "count-list-query",
      "steps": {
        "count": "onboarding-controller-query-onboarding-info-count",
        "list": "onboarding-controller-query-onboarding-info-list"
      },
      "inputs": {"name": "nameConcat"},
      "defaults": {"pageSize": 20, "pageNo": 1, "startIndex": 0, "queryType": 0}
    }
  ]
}
JSON

cd /media/vdc/code/repo-to-skill
python -m repo_to_skill.cli analyze /media/vdc/code/job/zte-hrm-job-service --output "$WORKDIR/analysis"
python -m repo_to_skill.cli generate /media/vdc/code/job/zte-hrm-job-service \
  --analysis "$WORKDIR/analysis" \
  --output "$WORKDIR/skill" \
  --mode task-workflow \
  --need "按姓名查询入职简历记录" \
  --workflow-hints "$HINTS" \
  --language zh-CN
```

Expected: the command prints `Generated task-workflow skill: ...` and `Validation: PASS`. The generated skill lives at `$WORKDIR/skill/<bundle-slug>/`.

If the slug names in the analysis differ (the analyzer assigns slugs from source), adjust the hints file to match the slugs printed in `$WORKDIR/analysis/callable_capabilities.json`. The smoke test is about the round-trip working, not the exact slug names.

### Step 3: dry-run the generated runner

Pick the generated `scripts/run_query_resume_records.py` and invoke it without env vars:

```bash
python "$WORKDIR/skill"/*/scripts/run_query_resume_records.py --name "张三"
```

Expected: exit code 0, output starts with `[dry-run]`, prints the planned payload, prints `<ZTE_HRM_ONBOARDING_BASE_URL>` for the endpoints (because env is unset), and contains no token.

### Step 4: clean up

```bash
rm -rf "$WORKDIR"
```

### Step 5: confirm git state is clean

Run: `cd /media/vdc/code/repo-to-skill && git status --short`
Expected: clean (no uncommitted source changes). The `docs/superpowers/` planning directory may still appear as untracked if you skip committing it; that's acceptable.

### Step 6: commit any smoke-test-driven fixes (only if needed)

If Steps 1–3 surfaced a defect, fix it with the smallest possible change, re-run the relevant tests, and commit:

```bash
git commit -m "fix(skillgen): <specific regression>"
```

If no defect surfaced, **do not create an empty commit**. Just report the clean state.

---

## Self-review (run after writing, not as a dispatched subagent)

**Spec coverage:**
- single-query supported end-to-end? → Task 7 (loader already accepts; planner Step 4; runner Step 6; tests Steps 3 & 5).
- lookup-detail rejected with a clear message? → Task 7 Step 2.
- Documentation updated for task-workflow? → Task 8.
- Full regression sweep on the HRM sample? → Task 9.

**Placeholder scan:** All steps contain concrete code or commands; no "TBD" / "implement later".

**Type consistency:** `WorkflowHint`/`WorkflowHintStep`/`WorkflowHints` already exist in `workflow_hints.py` and are imported in both test files. `_prepare_single_query` mirrors `_prepare` already present in `tests/test_workflow_planner.py`. The runner template uses `workflow.steps[0].role` consistently with how `WorkflowPlan.steps` is built.

**Naming consistency:** `single-query`, `count-list-query`, `lookup-detail` are the canonical pattern names everywhere; service env names follow `<PREFIX>_BASE_URL` / `<PREFIX>_TOKEN` from Task 2.

---

## Execution handoff

Plan complete and saved to `/media/vdc/code/repo-to-skill/docs/superpowers/plans/2026-07-03-repo-to-skill-task-workflow.md`. The branch `feat/task-workflow` is mid-execution via `superpowers:subagent-driven-development`; continue dispatching fresh subagents per task with the same two-stage review pattern used for Tasks 1–6.
