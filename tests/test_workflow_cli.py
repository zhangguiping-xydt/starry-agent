from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repo_to_skill.cli import app


runner = CliRunner()


def _write_synthetic_analysis(analysis_dir: Path) -> tuple[str, str]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    slug_count = "example-query-count"
    slug_list = "example-query-list"
    interfaces = [
        {
            "slug": slug_count,
            "stack": "java",
            "framework": "spring",
            "http_method": "POST",
            "route": "/example/querycount",
            "handler_symbol": "Controller.example_query_count",
            "handler_path": "src/main/java/example/Controller.java",
            "business_method": "Service.example_query_count",
            "endpoint_env": "EXAMPLE_QUERY_COUNT_ENDPOINT",
            "token_env": "EXAMPLE_QUERY_COUNT_TOKEN",
            "side_effects": "read",
            "request": {
                "model_name": "ExampleQueryCountRequest",
                "fields": [{"name": "nameConcat", "type": "string", "required": False}],
                "unresolved": False,
                "notes": [],
            },
            "response": {"model_name": "ExampleQueryCountResponse", "fields": [], "unresolved": False, "notes": []},
        },
        {
            "slug": slug_list,
            "stack": "java",
            "framework": "spring",
            "http_method": "POST",
            "route": "/example/querylist",
            "handler_symbol": "Controller.example_query_list",
            "handler_path": "src/main/java/example/Controller.java",
            "business_method": "Service.example_query_list",
            "endpoint_env": "EXAMPLE_QUERY_LIST_ENDPOINT",
            "token_env": "EXAMPLE_QUERY_LIST_TOKEN",
            "side_effects": "read",
            "request": {
                "model_name": "ExampleQueryListRequest",
                "fields": [{"name": "nameConcat", "type": "string", "required": False}],
                "unresolved": False,
                "notes": [],
            },
            "response": {"model_name": "ExampleQueryListResponse", "fields": [], "unresolved": False, "notes": []},
        },
    ]
    (analysis_dir / "scan.json").write_text(
        json.dumps({"root": "<synthetic>", "files": []}), encoding="utf-8"
    )
    (analysis_dir / "profile.json").write_text(
        json.dumps({"name": "example-service"}), encoding="utf-8"
    )
    (analysis_dir / "callable_capabilities.json").write_text(
        json.dumps({"project": "example-service", "interfaces": interfaces, "notes": []}),
        encoding="utf-8",
    )
    return slug_count, slug_list


def _write_hints(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hints.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_generate_task_workflow_passes_validate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    output = tmp_path / "skill"

    slug_count, slug_list = _write_synthetic_analysis(analysis)

    hints = _write_hints(
        tmp_path,
        {
            "service_env_prefix": "EXAMPLE_SERVICE",
            "workflows": [
                {
                    "name": "query_records",
                    "pattern": "count-list-query",
                    "steps": {
                        "count": slug_count,
                        "list": slug_list,
                    },
                    "inputs": {"keyword": "nameConcat"},
                    "defaults": {"pageSize": 20, "pageNo": 1, "startIndex": 0},
                }
            ],
        },
    )

    result = runner.invoke(
        app,
        [
            "generate",
            str(repo),
            "--analysis",
            str(analysis),
            "--output",
            str(output),
            "--mode",
            "task-workflow",
            "--need",
            "按关键词查询记录",
            "--workflow-hints",
            str(hints),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Validation: PASS" in result.stdout


def test_cli_generate_task_workflow_without_hints_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis = tmp_path / "analysis"
    output = tmp_path / "skill"
    _write_synthetic_analysis(analysis)

    result = runner.invoke(
        app,
        [
            "generate",
            str(repo),
            "--analysis",
            str(analysis),
            "--output",
            str(output),
            "--mode",
            "task-workflow",
            "--need",
            "anything",
        ],
    )

    assert result.exit_code != 0
    assert "task-workflow" in result.stdout
    assert "Traceback" not in result.stdout
