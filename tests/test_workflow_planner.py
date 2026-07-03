from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_to_skill.skillgen.workflow_hints import (
    WorkflowHints,
    load_workflow_hints,
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
