from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

from repo_to_skill.skillgen.workflow_hints import (
    WorkflowHint,
    WorkflowHints,
    WorkflowHintStep,
)
from repo_to_skill.skillgen.workflow_planner import plan_task_workflow
from repo_to_skill.skillgen.renderer import render_task_workflow
from repo_to_skill.skillgen.validator import validate_skill


def _interface(slug: str, route: str) -> dict:
    module = slug.replace("-", "_")
    return {
        "slug": slug,
        "stack": "java",
        "framework": "spring",
        "http_method": "POST",
        "route": route,
        "handler_symbol": "Controller." + module,
        "handler_path": "src/main/java/example/Controller.java",
        "business_method": "Service." + module,
        "endpoint_env": module.upper() + "_ENDPOINT",
        "token_env": module.upper() + "_TOKEN",
        "side_effects": "read",
        "request": {
            "model_name": module + "Request",
            "fields": [
                {"name": "nameConcat", "type": "string", "required": False},
                {"name": "pageSize", "type": "Long", "required": False},
                {"name": "pageNo", "type": "Long", "required": False},
                {"name": "startIndex", "type": "Long", "required": False},
            ],
            "unresolved": False,
            "notes": [],
        },
        "response": {"model_name": module + "Response", "fields": [], "unresolved": False, "notes": []},
    }


def _prepare(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interfaces = [
        _interface("example-query-count", "/example/querycount"),
        _interface("example-query-list", "/example/querylist"),
    ]
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "zte-hrm-job-service"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "zte-hrm-job-service", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    return repo, analysis


def _prepare_single(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interfaces = [_interface("example-query", "/example/query")]
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "zte-hrm-job-service"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "zte-hrm-job-service", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    return repo, analysis


def _hints() -> WorkflowHints:
    return WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="query_records",
                pattern="count-list-query",
                steps=(
                    WorkflowHintStep("count", "example-query-count"),
                    WorkflowHintStep("list", "example-query-list"),
                ),
                inputs={"keyword": "nameConcat"},
                defaults={"pageSize": 20, "pageNo": 1, "startIndex": 0},
            ),
        ),
    )


def test_render_task_workflow_creates_full_layout(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )

    skill = render_task_workflow(plan, tmp_path / "skill")

    assert skill.is_dir()
    assert (skill / "SKILL.md").is_file()
    assert (skill / "manifest.yaml").is_file()
    assert sorted(path.name for path in (skill / "workflows").glob("*.yaml")) == ["query_records.yaml"]
    assert sorted(path.name for path in (skill / "scripts").glob("call_*.py")) == [
        "call_example_query_count.py",
        "call_example_query_list.py",
    ]
    assert (skill / "scripts" / "run_query_records.py").is_file()
    assert sorted(path.name for path in (skill / "tools").glob("*.tool.yaml")) == [
        "example_query_count.tool.yaml",
        "example_query_list.tool.yaml",
    ]
    assert (skill / "references" / "workflow-source.md").is_file()
    assert (skill / "references" / "service-config.md").is_file()


def test_render_task_workflow_manifest_has_service_block(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )

    skill = render_task_workflow(plan, tmp_path / "skill")
    manifest = yaml.safe_load((skill / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest["kind"] == "task-workflow"
    assert manifest["service"]["env_prefix"] == "EXAMPLE_SERVICE"
    assert manifest["service"]["base_url_env"] == "EXAMPLE_SERVICE_BASE_URL"
    assert manifest["service"]["token_env"] == "EXAMPLE_SERVICE_TOKEN"
    assert [iface["slug"] for iface in manifest["interfaces"]] == [
        "example-query-count",
        "example-query-list",
    ]


def test_render_task_workflow_runner_dry_run_does_not_send(monkeypatch, tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    skill = render_task_workflow(plan, tmp_path / "skill")

    runner_path = skill / "scripts" / "run_query_records.py"
    spec = importlib.util.spec_from_file_location("task_workflow_runner", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _no_call(*_args, **_kwargs):
        raise AssertionError("runner must not send a request in dry-run mode")

    monkeypatch.setattr(module, "_send_request", _no_call)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--keyword", "Alice"])

    assert rc == 0
    out = buffer.getvalue()
    assert "[dry-run]" in out
    assert "EXAMPLE_SERVICE_BASE_URL" in out or "/example/querycount" in out
    assert "secret" not in out

    monkeypatch.setenv("EXAMPLE_SERVICE_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("EXAMPLE_SERVICE_TOKEN", "secret")
    with pytest.raises(AssertionError, match="runner must not send"):
        module.main(["--keyword", "Alice", "--execute"])


def test_render_task_workflow_execute_without_token_falls_back_to_dry_run(
    monkeypatch, tmp_path: Path
) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    skill = render_task_workflow(plan, tmp_path / "skill")

    runner_path = skill / "scripts" / "run_query_records.py"
    spec = importlib.util.spec_from_file_location("task_workflow_runner_no_token", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[object] = []

    def _no_call(*args, **_kwargs):
        calls.append(args)
        raise AssertionError("runner must not send a request without a token")

    monkeypatch.setattr(module, "_send_request", _no_call)
    monkeypatch.setenv("EXAMPLE_SERVICE_BASE_URL", "https://example.invalid")
    monkeypatch.delenv("EXAMPLE_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("EXAMPLE_QUERY_COUNT_TOKEN", raising=False)
    monkeypatch.delenv("EXAMPLE_QUERY_LIST_TOKEN", raising=False)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--execute", "--keyword", "Alice"])

    assert rc == 0
    out = buffer.getvalue()
    assert "[dry-run]" in out
    assert "EXAMPLE_QUERY_COUNT_TOKEN" in out
    assert "EXAMPLE_QUERY_LIST_TOKEN" in out
    assert calls == []


def test_render_task_workflow_count_list_query_uses_each_step_token(
    monkeypatch, tmp_path: Path
) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    skill = render_task_workflow(plan, tmp_path / "skill")

    runner_path = skill / "scripts" / "run_query_records.py"
    spec = importlib.util.spec_from_file_location("task_workflow_runner_step_tokens", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    authorizations: list[str | None] = []

    def _capture(request, _timeout):
        authorizations.append(request.get_header("Authorization"))
        if len(authorizations) == 1:
            return json.dumps({"bo": 1})
        return json.dumps({"rows": []})

    monkeypatch.setattr(module, "_send_request", _capture)
    monkeypatch.setenv("EXAMPLE_SERVICE_BASE_URL", "https://example.invalid")
    monkeypatch.delenv("EXAMPLE_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("EXAMPLE_QUERY_COUNT_TOKEN", "count-secret")
    monkeypatch.setenv("EXAMPLE_QUERY_LIST_TOKEN", "list-secret")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--execute", "--keyword", "Alice"])

    assert rc == 0
    assert authorizations == ["Bearer count-secret", "Bearer list-secret"]


def test_render_task_workflow_single_query_execute_without_token_falls_back_to_dry_run(
    monkeypatch, tmp_path: Path
) -> None:
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
    spec = importlib.util.spec_from_file_location("task_workflow_runner_single_no_token", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[object] = []

    def _no_call(*args, **_kwargs):
        calls.append(args)
        raise AssertionError("runner must not send a request without a token")

    monkeypatch.setattr(module, "_send_request", _no_call)
    monkeypatch.setenv("EXAMPLE_SERVICE_BASE_URL", "https://example.invalid")
    monkeypatch.delenv("EXAMPLE_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("EXAMPLE_QUERY_TOKEN", raising=False)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--execute", "--keyword", "Alice"])

    assert rc == 0
    out = buffer.getvalue()
    assert "[dry-run]" in out
    assert "EXAMPLE_QUERY_TOKEN" in out
    assert calls == []


def test_render_task_workflow_disambiguates_colliding_step_modules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interfaces = [
        _interface("example-query-count", "/routes/from-hyphen"),
        _interface("example_query_count", "/routes/from-underscore"),
    ]
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "zte-hrm-job-service"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "zte-hrm-job-service", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="hyphen_lookup",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-query-count"),),
                inputs={},
                defaults={},
            ),
            WorkflowHint(
                name="underscore_lookup",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example_query_count"),),
                inputs={},
                defaults={},
            ),
        ),
    )
    plan = plan_task_workflow(repo, analysis, hints=hints, need_summary="查重", language="zh-CN")

    skill = render_task_workflow(plan, tmp_path / "skill")

    tool_files = sorted(path.name for path in (skill / "tools").glob("*.tool.yaml"))
    script_files = sorted(path.name for path in (skill / "scripts").glob("call_*.py"))
    assert len(tool_files) == 2
    assert len(script_files) == 2
    assert len(set(tool_files)) == 2
    assert len(set(script_files)) == 2
    assert "example_query_count.tool.yaml" in tool_files
    assert "call_example_query_count.py" in script_files

    hyphen_workflow = yaml.safe_load((skill / "workflows" / "hyphen_lookup.yaml").read_text(encoding="utf-8"))
    underscore_workflow = yaml.safe_load(
        (skill / "workflows" / "underscore_lookup.yaml").read_text(encoding="utf-8")
    )
    assert hyphen_workflow["steps"][0]["route"] == "/routes/from-hyphen"
    assert underscore_workflow["steps"][0]["route"] == "/routes/from-underscore"


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


def test_render_task_workflow_validates(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    skill = render_task_workflow(plan, tmp_path / "skill")

    report = validate_skill(skill)

    assert report.status == "PASS", report.findings
