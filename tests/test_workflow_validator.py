from __future__ import annotations

from pathlib import Path

from repo_to_skill.skillgen.renderer import render_task_workflow
from repo_to_skill.skillgen.workflow_hints import (
    WorkflowHint,
    WorkflowHintStep,
    WorkflowHints,
)
from repo_to_skill.skillgen.workflow_planner import plan_task_workflow
from repo_to_skill.skillgen.validator import validate_skill

import json


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


def _rendered_skill(tmp_path: Path) -> Path:
    repo, analysis = _prepare(tmp_path)
    plan = plan_task_workflow(
        repo, analysis, hints=_hints(), need_summary="按关键词查询记录", language="zh-CN"
    )
    return render_task_workflow(plan, tmp_path / "skill")


def test_task_workflow_skill_validates(tmp_path: Path) -> None:
    skill = _rendered_skill(tmp_path)

    report = validate_skill(skill)

    assert report.status == "PASS", report.findings


def test_task_workflow_validator_flags_missing_workflow_file(tmp_path: Path) -> None:
    skill = _rendered_skill(tmp_path)
    (skill / "workflows" / "query_records.yaml").unlink()

    report = validate_skill(skill)

    assert report.status == "FAIL"
    assert any("workflows/" in finding for finding in report.findings)


def test_task_workflow_validator_flags_non_string_workflow_file(tmp_path: Path) -> None:
    skill = _rendered_skill(tmp_path)
    manifest_path = skill / "manifest.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_text = manifest_text.replace(
        "file: workflows/query_records.yaml",
        'file: ["workflows/query_records.yaml"]',
    )
    manifest_path.write_text(manifest_text, encoding="utf-8")

    report = validate_skill(skill)

    assert report.status == "FAIL"
    assert any("string name and file" in finding for finding in report.findings)


def test_task_workflow_validator_flags_write_interface(tmp_path: Path) -> None:
    skill = _rendered_skill(tmp_path)
    manifest_path = skill / "manifest.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_text = manifest_text.replace("side_effects: read", "side_effects: write")
    manifest_path.write_text(manifest_text, encoding="utf-8")

    report = validate_skill(skill)

    assert report.status == "FAIL"
    assert any("write" in finding.lower() or "side_effect" in finding.lower() for finding in report.findings)


def test_task_workflow_validator_flags_hardcoded_token(tmp_path: Path) -> None:
    skill = _rendered_skill(tmp_path)
    runner = skill / "scripts" / "run_query_records.py"
    runner.write_text(
        runner.read_text(encoding="utf-8").replace(
            "os.environ.get(TOKEN_ENV)",
            '"hardcoded-token"',
        ),
        encoding="utf-8",
    )

    report = validate_skill(skill)

    assert report.status == "FAIL"
    assert any("hardcoded" in finding.lower() or "token" in finding.lower() for finding in report.findings)
