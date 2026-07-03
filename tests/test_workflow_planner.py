from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_to_skill.skillgen.workflow_hints import (
    WorkflowHint,
    WorkflowHints,
    WorkflowHintStep,
    load_workflow_hints,
)
from repo_to_skill.skillgen.workflow_planner import (
    derive_service_env_prefix,
    plan_task_workflow,
    service_env_names,
)


def _write_hints(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hints.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_workflow_hints_parses_service_prefix(tmp_path: Path) -> None:
    path = _write_hints(
        tmp_path,
        {
            "service_env_prefix": "EXAMPLE_SERVICE",
            "workflows": [],
        },
    )

    hints = load_workflow_hints(path)

    assert isinstance(hints, WorkflowHints)
    assert hints.service_env_prefix == "EXAMPLE_SERVICE"
    assert hints.workflows == ()


def test_load_workflow_hints_requires_service_env_prefix(tmp_path: Path) -> None:
    path = _write_hints(tmp_path, {"workflows": []})

    with pytest.raises(ValueError, match="service_env_prefix"):
        load_workflow_hints(path)


def test_load_workflow_hints_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    path = _write_hints(
        tmp_path,
        {"service_env_prefix": "EXAMPLE_SERVICE", "bogus": 1, "workflows": []},
    )

    with pytest.raises(ValueError, match="unknown hints key: bogus"):
        load_workflow_hints(path)


def test_load_workflow_hints_rejects_non_list_workflows(tmp_path: Path) -> None:
    path = _write_hints(tmp_path, {"service_env_prefix": "X", "workflows": {}})

    with pytest.raises(ValueError, match="workflows must be a list"):
        load_workflow_hints(path)


def test_service_env_prefix_converts_project_name() -> None:
    assert derive_service_env_prefix("zte-hrm-job-service") == "ZTE_HRM_JOB_SERVICE"
    assert derive_service_env_prefix("corehr-businessprocess") == "COREHR_BUSINESSPROCESS"
    assert derive_service_env_prefix("---") == "LOCAL_REPOSITORY"
    assert derive_service_env_prefix("foo---bar___baz") == "FOO_BAR_BAZ"


def test_service_env_names_build_base_url_and_token_envs() -> None:
    names = service_env_names("ZTE_HRM_JOB_SERVICE")

    assert names == {
        "env_prefix": "ZTE_HRM_JOB_SERVICE",
        "base_url_env": "ZTE_HRM_JOB_SERVICE_BASE_URL",
        "token_env": "ZTE_HRM_JOB_SERVICE_TOKEN",
    }


def _interface(slug: str, route: str, side_effects: str = "read") -> dict:
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
        "side_effects": side_effects,
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


def _capabilities(interfaces: list[dict]) -> dict:
    return {"project": "zte-hrm-job-service", "interfaces": interfaces, "notes": []}


def _analysis(tmp_path: Path, interfaces: list[dict]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "zte-hrm-job-service"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps(_capabilities(interfaces)), encoding="utf-8"
    )
    return repo, analysis


def test_plan_task_workflow_count_list_query(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-query-count", "/example/querycount", side_effects="read"),
        _interface("example-query-list", "/example/querylist", side_effects="read"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
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

    plan = plan_task_workflow(
        repo,
        analysis,
        hints=hints,
        need_summary="按关键词查询记录",
        language="zh-CN",
    )

    assert plan.service.env_prefix == "EXAMPLE_SERVICE"
    assert len(plan.workflows) == 1
    workflow = plan.workflows[0]
    assert workflow.name == "query_records"
    assert workflow.pattern == "count-list-query"
    assert [step.role for step in workflow.steps] == ["count", "list"]
    assert [step.slug for step in workflow.steps] == ["example-query-count", "example-query-list"]
    assert workflow.inputs[0].name == "keyword"
    assert workflow.inputs[0].maps_to == "nameConcat"


def test_task_workflow_plan_has_project_name_property(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-query", "/example/query", side_effects="read"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="query_records",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-query"),),
                inputs={},
                defaults={},
            ),
        ),
    )

    plan = plan_task_workflow(
        repo,
        analysis,
        hints=hints,
        need_summary="按关键词查询记录",
        language="zh-CN",
    )

    assert plan.project_name == plan.service.name == "zte-hrm-job-service"


def test_plan_task_workflow_rejects_count_list_wrong_roles(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-query-count", "/example/querycount", side_effects="read"),
        _interface("example-query-list", "/example/querylist", side_effects="read"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="query_records",
                pattern="count-list-query",
                steps=(
                    WorkflowHintStep("list", "example-query-list"),
                    WorkflowHintStep("count", "example-query-count"),
                ),
                inputs={},
                defaults={},
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"query_records.*count-list-query requires steps",
    ):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="查询", language="en")


def test_plan_task_workflow_rejects_unsafe_workflow_name(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-query", "/example/query", side_effects="read"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="bad/name",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-query"),),
                inputs={},
                defaults={},
            ),
        ),
    )

    with pytest.raises(ValueError, match="workflow name is not a safe slug"):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="查询", language="en")


def test_plan_task_workflow_rejects_duplicate_workflow_names(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-query", "/example/query", side_effects="read"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="query_records",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-query"),),
                inputs={},
                defaults={},
            ),
            WorkflowHint(
                name="query_records",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-query"),),
                inputs={},
                defaults={},
            ),
        ),
    )

    with pytest.raises(ValueError, match="duplicate workflow name"):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="查询", language="en")


def test_plan_task_workflow_rejects_write_interface(tmp_path: Path) -> None:
    interfaces = [
        _interface("example-save", "/example/save", side_effects="write"),
    ]
    repo, analysis = _analysis(tmp_path, interfaces)
    hints = WorkflowHints(
        service_env_prefix="EXAMPLE_SERVICE",
        workflows=(
            WorkflowHint(
                name="save_record",
                pattern="single-query",
                steps=(WorkflowHintStep("lookup", "example-save"),),
                inputs={},
                defaults={},
            ),
        ),
    )

    with pytest.raises(ValueError, match="write interface"):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="保存", language="en")


def test_plan_task_workflow_fails_without_hints_when_pattern_unknown(tmp_path: Path) -> None:
    interfaces = [_interface("example-only", "/example/only")]
    repo, analysis = _analysis(tmp_path, interfaces)

    with pytest.raises(ValueError, match="cannot generate task-workflow"):
        plan_task_workflow(repo, analysis, hints=None, need_summary="anything", language="en")


def test_plan_task_workflow_wraps_missing_artifact(tmp_path: Path) -> None:
    interfaces = [_interface("example-query", "/example/query", side_effects="read")]
    repo, analysis = _analysis(tmp_path, interfaces)
    (analysis / "callable_capabilities.json").unlink()

    hints = WorkflowHints(service_env_prefix="EXAMPLE_SERVICE", workflows=())

    with pytest.raises(ValueError, match="missing analysis artifact"):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="查询", language="en")


def test_plan_task_workflow_wraps_invalid_json(tmp_path: Path) -> None:
    interfaces = [_interface("example-query", "/example/query", side_effects="read")]
    repo, analysis = _analysis(tmp_path, interfaces)
    (analysis / "callable_capabilities.json").write_text("not json", encoding="utf-8")

    hints = WorkflowHints(service_env_prefix="EXAMPLE_SERVICE", workflows=())

    with pytest.raises(ValueError, match="invalid analysis artifact"):
        plan_task_workflow(repo, analysis, hints=hints, need_summary="查询", language="en")
