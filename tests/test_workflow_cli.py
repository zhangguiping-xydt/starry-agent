from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repo_to_skill.cli import app


runner = CliRunner()


def _callable_repo() -> Path:
    return Path(__file__).resolve().parents[1] / "repo_to_skill" / "resources" / "examples" / "callable-multistack"


def _write_hints(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hints.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_generate_task_workflow_passes_validate(tmp_path: Path) -> None:
    repo = _callable_repo()
    analysis = tmp_path / "analysis"
    output = tmp_path / "skill"
    analyze = runner.invoke(app, ["analyze", str(repo), "--output", str(analysis)])
    assert analyze.exit_code == 0, analyze.stdout

    caps = json.loads((analysis / "callable_capabilities.json").read_text(encoding="utf-8"))
    slugs = [iface["slug"] for iface in caps["interfaces"][:2]]
    if len(slugs) < 2:
        return
    hints = _write_hints(
        tmp_path,
        {
            "service_env_prefix": "EXAMPLE_SERVICE",
            "workflows": [
                {
                    "name": "query_records",
                    "pattern": "count-list-query",
                    "steps": {
                        "count": slugs[0],
                        "list": slugs[1],
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
    repo = _callable_repo()
    analysis = tmp_path / "analysis"
    output = tmp_path / "skill"
    analyze = runner.invoke(app, ["analyze", str(repo), "--output", str(analysis)])
    assert analyze.exit_code == 0, analyze.stdout

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
