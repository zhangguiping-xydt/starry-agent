from __future__ import annotations

import json
from pathlib import Path

import yaml

from repo_to_skill.skillgen.planner import plan_callable_bundle
from repo_to_skill.skillgen.renderer import render_callable_bundle
from repo_to_skill.skillgen.validator import validate_skill


def _interface(slug: str, *, route: str, handler: str, field: str) -> dict:
    env = slug.replace("-", "_").upper()
    return {
        "slug": slug,
        "stack": "java",
        "framework": "spring",
        "http_method": "POST",
        "route": route,
        "handler_symbol": handler,
        "handler_path": "src/main/java/example/Controller.java",
        "business_method": handler + "Service.execute",
        "endpoint_env": env + "_ENDPOINT",
        "token_env": env + "_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": handler.rsplit(".", 1)[-1] + "Request",
            "fields": [{"name": field, "type": "string", "required": True}],
            "unresolved": False,
            "notes": [],
        },
        "response": {
            "model_name": handler.rsplit(".", 1)[-1] + "Response",
            "fields": [{"name": field + "Result", "type": "string", "required": False}],
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
        _interface("employee-entry", route="/employee/entry", handler="EmployeeController.entry", field="employeeNo"),
        _interface("job-transfer", route="/job/transfer", handler="JobController.transfer", field="positionId"),
        _interface("dictionary-list", route="/dictionary/list", handler="DictionaryController.list", field="dicId"),
    ]
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "corehr-businessprocess"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "corehr-businessprocess", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    return repo, analysis


def test_plan_callable_bundle_selects_interfaces_from_need(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)

    plan = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=None,
        selection_json=None,
        max_interfaces=2,
    )

    assert plan.project_name == "corehr-businessprocess"
    assert plan.bundle_slug == "employee-job-transfer"
    assert [item.interface["slug"] for item in plan.selection.items] == [
        "job-transfer",
        "employee-entry",
    ]


def test_render_callable_bundle_creates_one_skill_with_multiple_tools(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=["employee-entry", "job-transfer"],
        selection_json=None,
        max_interfaces=5,
    )

    bundle = render_callable_bundle(plan, tmp_path / "skill")

    assert bundle.name == "employee-job-transfer"
    assert (bundle / "SKILL.md").is_file()
    assert (bundle / "manifest.yaml").is_file()
    assert (bundle / "references" / "capability-selection.md").is_file()
    assert (bundle / "references" / "capability-source.md").is_file()
    assert sorted(path.name for path in (bundle / "tools").glob("*.tool.yaml")) == [
        "employee_entry.tool.yaml",
        "job_transfer.tool.yaml",
    ]
    assert sorted(path.name for path in (bundle / "scripts").glob("call_*.py")) == [
        "call_employee_entry.py",
        "call_job_transfer.py",
    ]

    manifest = yaml.safe_load((bundle / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["kind"] == "callable-bundle"
    assert manifest["selection"]["interfaces_count"] == 2
    assert manifest["selection"]["source"] == "agentic"
    assert manifest["safety"]["dry_run_default"] is True

    skill = (bundle / "SKILL.md").read_text(encoding="utf-8")
    assert "employee-entry" in skill
    assert "job-transfer" in skill
    selection = (bundle / "references" / "capability-selection.md").read_text(encoding="utf-8")
    assert "selected by agent slug" in selection
    assert "employee-entry" in selection


def test_render_callable_bundle_removes_stale_tools_and_scripts(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    output = tmp_path / "skill"

    first = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=["employee-entry", "job-transfer"],
        selection_json=None,
        max_interfaces=5,
    )
    bundle = render_callable_bundle(first, output)
    assert (bundle / "tools" / "job_transfer.tool.yaml").is_file()

    second = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=["employee-entry"],
        selection_json=None,
        max_interfaces=5,
    )
    bundle = render_callable_bundle(second, output)

    assert sorted(path.name for path in (bundle / "tools").glob("*.tool.yaml")) == ["employee_entry.tool.yaml"]
    assert sorted(path.name for path in (bundle / "scripts").glob("call_*.py")) == ["call_employee_entry.py"]


def test_render_callable_bundle_rejects_symlink_skill_root(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    output = tmp_path / "skill"
    output.mkdir()
    protected = output / "protected"
    protected.mkdir()
    (protected / "keep.txt").write_text("keep", encoding="utf-8")
    (output / "employee-job-transfer").symlink_to(protected, target_is_directory=True)
    plan = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=["employee-entry"],
        selection_json=None,
        max_interfaces=5,
    )

    try:
        render_callable_bundle(plan, output)
    except ValueError as exc:
        assert "symlink" in str(exc).lower()
    else:
        raise AssertionError("symlink skill root must be rejected")

    assert (protected / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_rendered_callable_bundle_validates(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path)
    plan = plan_callable_bundle(
        repo,
        analysis,
        need="employee job transfer",
        selected_slugs=["employee-entry", "job-transfer"],
        selection_json=None,
        max_interfaces=5,
    )
    bundle = render_callable_bundle(plan, tmp_path / "skill")

    report = validate_skill(bundle)

    assert report.status == "PASS", report.findings
