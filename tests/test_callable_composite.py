from __future__ import annotations

import ast
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from repo_to_skill.skillgen.planner import plan_callable_composite
from repo_to_skill.skillgen.renderer import render_callable_composite
from repo_to_skill.skillgen.validator import validate_skill


def _interface(
    slug: str,
    *,
    route: str,
    handler: str,
    request_field: str,
    response_field: str,
    method: str = "POST",
) -> dict:
    env = slug.replace("-", "_").upper()
    return {
        "slug": slug,
        "stack": "java",
        "framework": "spring",
        "http_method": method,
        "route": route,
        "handler_symbol": handler,
        "handler_path": "src/main/java/example/Controller.java",
        "business_method": handler + "Service.execute",
        "endpoint_env": env + "_ENDPOINT",
        "token_env": env + "_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": handler.rsplit(".", 1)[-1] + "Request",
            "fields": [{"name": request_field, "type": "string", "required": True}],
            "unresolved": False,
            "notes": [],
        },
        "response": {
            "model_name": handler.rsplit(".", 1)[-1] + "Response",
            "fields": [{"name": response_field, "type": "string", "required": False}],
            "unresolved": False,
            "notes": [],
        },
    }


def _prepare(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interfaces = [
        _interface(
            "calculate-work-load",
            route="/workload/calculate",
            handler="WorkLoadController.calculate",
            request_field="EmployeeInfo",
            response_field="TimeLenthUintHour",
        ),
        _interface(
            "leave-balance",
            route="/leave/balance",
            handler="LeaveController.balance",
            request_field="WorkHours",
            response_field="CompLeaveDays",
        ),
        _interface(
            "dictionary-list",
            route="/dictionary/list",
            handler="DictionaryController.list",
            request_field="DicId",
            response_field="DicName",
        ),
    ]
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "tms-atm"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "tms-atm", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    return repo, analysis


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #


def test_plan_composite_preserves_selected_slug_order(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    assert plan.project_name == "tms-atm"
    assert plan.goal == "根据加班时长查询调休天数"
    assert [step.slug for step in plan.steps] == ["calculate-work-load", "leave-balance"]
    assert plan.steps[0].order == 0
    assert plan.steps[1].order == 1
    assert plan.selection.selection_source == "agentic"


def test_plan_composite_deterministic_fallback_picks_top_scoring(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    plan = plan_callable_composite(
        repo,
        analysis,
        goal="overtime work load comp leave",
        selected_slugs=None,
        selection_json=None,
        max_interfaces=2,
    )

    slugs = [step.slug for step in plan.steps]
    assert len(slugs) == 2
    assert "calculate-work-load" in slugs
    assert "leave-balance" in slugs
    assert plan.selection.selection_source == "deterministic"


def test_plan_composite_rejects_unknown_slug(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    try:
        plan_callable_composite(
            repo,
            analysis,
            goal="anything",
            selected_slugs=["calculate-work-load", "does-not-exist"],
            selection_json=None,
            max_interfaces=5,
        )
    except ValueError as exc:
        assert "does-not-exist" in str(exc)
    else:
        raise AssertionError("unknown slug must raise ValueError")


def test_plan_composite_requires_at_least_two_slugs(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    try:
        plan_callable_composite(
            repo,
            analysis,
            goal="anything",
            selected_slugs=["calculate-work-load"],
            selection_json=None,
            max_interfaces=5,
        )
    except ValueError as exc:
        assert "at least 2" in str(exc).lower() or "two" in str(exc).lower()
    else:
        raise AssertionError("single slug must raise ValueError")


def test_plan_composite_respects_max_interfaces(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    plan = plan_callable_composite(
        repo,
        analysis,
        goal="overtime leave dictionary workload balance",
        selected_slugs=None,
        selection_json=None,
        max_interfaces=2,
    )

    assert len(plan.steps) <= 2


def test_plan_composite_loads_selection_json(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    selection_json = tmp_path / "selection.json"
    selection_json.write_text(
        json.dumps(
            {
                "need_summary": "根据加班时长查询调休天数",
                "selected_slugs": ["calculate-work-load", "leave-balance"],
                "selection_source": "agentic",
            }
        ),
        encoding="utf-8",
    )

    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=None,
        selection_json=selection_json,
        max_interfaces=5,
    )

    assert [step.slug for step in plan.steps] == ["calculate-work-load", "leave-balance"]
    assert plan.selection.selection_source == "agentic"


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #


def test_render_composite_creates_one_skill_with_orchestrator_and_callers(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")

    assert composite.is_dir()
    assert (composite / "SKILL.md").is_file()
    assert (composite / "manifest.yaml").is_file()
    assert (composite / "orchestrator.py").is_file()
    assert (composite / "references" / "composition.md").is_file()
    assert (composite / "references" / "capability-source.md").is_file()
    assert sorted(path.name for path in (composite / "tools").glob("*.tool.yaml")) == [
        "calculate_work_load.tool.yaml",
        "leave_balance.tool.yaml",
    ]
    assert sorted(path.name for path in (composite / "scripts").glob("call_*.py")) == [
        "call_calculate_work_load.py",
        "call_leave_balance.py",
    ]


def test_render_composite_removes_stale_tools_and_scripts(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    output = tmp_path / "skill"
    first = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance", "dictionary-list"],
        selection_json=None,
        max_interfaces=5,
    )
    composite = render_callable_composite(first, output)
    assert (composite / "tools" / "dictionary_list.tool.yaml").is_file()

    second = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )
    composite = render_callable_composite(second, output)

    assert sorted(path.name for path in (composite / "tools").glob("*.tool.yaml")) == [
        "calculate_work_load.tool.yaml",
        "leave_balance.tool.yaml",
    ]
    assert sorted(path.name for path in (composite / "scripts").glob("call_*.py")) == [
        "call_calculate_work_load.py",
        "call_leave_balance.py",
    ]


def test_render_composite_orchestrator_parses_and_has_field_mapping_todos(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    orchestrator = composite / "orchestrator.py"
    source = orchestrator.read_text(encoding="utf-8")

    ast.parse(source)
    assert "# TODO: fill from step_" in source
    assert "CALL_CALCULATE_WORK_LOAD_ENDPOINT" in source or "CALCULATE_WORK_LOAD_ENDPOINT" in source
    assert "CALL_LEAVE_BALANCE_ENDPOINT" in source or "LEAVE_BALANCE_ENDPOINT" in source
    assert "step_0" in source
    assert "step_1" in source


def test_composite_orchestrator_uses_first_step_request_fields(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["leave-balance", "dictionary-list"],
        selection_json=None,
        max_interfaces=5,
    )
    composite = render_callable_composite(plan, tmp_path / "skill")
    orchestrator = composite / "orchestrator.py"
    source = orchestrator.read_text(encoding="utf-8")

    assert "--work-hours" in source
    assert "--employee-info" not in source

    spec = importlib.util.spec_from_file_location("dynamic_orchestrator", orchestrator)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--work-hours", "8"])

    assert rc == 0
    assert "--work-hours" in buffer.getvalue()


def test_composite_orchestrator_supports_boolean_first_step_args(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    interfaces = [
        _interface(
            "toggle-flag",
            route="/flags/toggle",
            handler="FlagController.toggle",
            request_field="Enabled",
            response_field="FlagId",
        ),
        _interface(
            "dictionary-list",
            route="/dictionary/list",
            handler="DictionaryController.list",
            request_field="DicId",
            response_field="DicName",
        ),
    ]
    interfaces[0]["request"]["fields"][0]["type"] = "boolean"
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "tms-atm"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "tms-atm", "interfaces": interfaces, "notes": []}), encoding="utf-8"
    )
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="toggle then lookup",
        selected_slugs=["toggle-flag", "dictionary-list"],
        selection_json=None,
        max_interfaces=5,
    )
    composite = render_callable_composite(plan, tmp_path / "skill")
    orchestrator = composite / "orchestrator.py"

    spec = importlib.util.spec_from_file_location("boolean_orchestrator", orchestrator)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--enabled", "true"])

    assert rc == 0
    assert "--enabled" in buffer.getvalue()



def test_render_composite_manifest_has_composite_kind_and_steps(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    manifest = yaml.safe_load((composite / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest["kind"] == "callable-composite"
    assert manifest["composition"]["goal"] == "根据加班时长查询调休天数"
    assert [step["slug"] for step in manifest["composition"]["steps"]] == [
        "calculate-work-load",
        "leave-balance",
    ]
    assert manifest["safety"]["dry_run_default"] is True
    assert manifest["safety"]["network"] == "requires-explicit-endpoint"


def test_render_composite_composition_md_lists_mapping_todos(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    composition = (composite / "references" / "composition.md").read_text(encoding="utf-8")

    assert "step_0" in composition
    assert "step_1" in composition
    assert "TODO" in composition
    assert "calculate-work-load" in composition
    assert "leave-balance" in composition
    assert "TimeLenthUintHour" in composition
    assert "WorkHours" in composition


def test_render_composite_no_machine_path_leak(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    for path in composite.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "/media/" not in text
            assert "/home/" not in text
            assert "/tmp/" not in text


def test_render_composite_orchestrator_dry_run_preview(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    orchestrator = composite / "orchestrator.py"

    spec = importlib.util.spec_from_file_location("composite_orchestrator", orchestrator)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = module.main(["--employee-info", "E1"])
    out = buffer.getvalue()

    assert rc == 0
    assert "[preview]" in out or "[step" in out.lower()


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #


def test_rendered_composite_validates(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    report = validate_skill(composite)
    assert report.status == "PASS", report.findings


def test_validator_fails_when_orchestrator_missing_field_mapping_todo(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    orchestrator = composite / "orchestrator.py"
    orchestrator.write_text(
        orchestrator.read_text(encoding="utf-8").replace("# TODO: fill from step_", "# filled"),
        encoding="utf-8",
    )

    report = validate_skill(composite)
    assert report.status == "FAIL"
    assert any("TODO" in finding for finding in report.findings)


def test_validator_fails_when_orchestrator_missing(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_composite(
        repo,
        analysis,
        goal="根据加班时长查询调休天数",
        selected_slugs=["calculate-work-load", "leave-balance"],
        selection_json=None,
        max_interfaces=5,
    )

    composite = render_callable_composite(plan, tmp_path / "skill")
    (composite / "orchestrator.py").unlink()

    report = validate_skill(composite)
    assert report.status == "FAIL"
    assert any("orchestrator" in finding.lower() for finding in report.findings)
