from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

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


def test_render_task_workflow_validates(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    skill = render_task_workflow(plan, tmp_path / "skill")

    report = validate_skill(skill)

    assert report.status == "PASS", report.findings
