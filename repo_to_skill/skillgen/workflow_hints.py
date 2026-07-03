from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowHintStep:
    role: str
    slug: str


@dataclass(frozen=True)
class WorkflowHint:
    name: str
    pattern: str
    steps: tuple[WorkflowHintStep, ...]
    inputs: dict[str, str]
    defaults: dict[str, Any]


@dataclass(frozen=True)
class WorkflowHints:
    service_env_prefix: str
    workflows: tuple[WorkflowHint, ...]


_KNOWN_STEP_ROLES = {"count", "list", "detail", "lookup"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_workflow_hints(path: Path) -> WorkflowHints:
    raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    _require(isinstance(raw, dict), "workflow hints root must be a mapping")

    unknown_keys = set(raw) - {"service_env_prefix", "workflows"}
    _require(not unknown_keys, "unknown hints key: " + ", ".join(sorted(unknown_keys)))

    service_env_prefix = str(raw.get("service_env_prefix") or "").strip()
    _require(
        service_env_prefix.replace("_", "").isalnum() and service_env_prefix.isupper(),
        "service_env_prefix must be UPPER_SNAKE_CASE",
    )

    raw_workflows = raw.get("workflows", [])
    _require(isinstance(raw_workflows, list), "workflows must be a list")

    workflows: list[WorkflowHint] = []
    for index, raw_workflow in enumerate(raw_workflows):
        workflow_path = f"workflows[{index}]"
        _require(isinstance(raw_workflow, dict), f"{workflow_path} must be a mapping")
        name = str(raw_workflow.get("name") or "").strip()
        pattern = str(raw_workflow.get("pattern") or "").strip()
        _require(name, f"{workflow_path} name must be set")
        workflow_path = f"workflows[{index}] ({name})"
        _require(
            pattern in {"single-query", "count-list-query", "lookup-detail"},
            f"{workflow_path} unsupported workflow pattern: {pattern}",
        )

        raw_steps = raw_workflow.get("steps", {})
        _require(isinstance(raw_steps, dict), f"{workflow_path}.steps must be a mapping")
        parsed_steps: list[WorkflowHintStep] = []
        for role, slug in raw_steps.items():
            _require(role in _KNOWN_STEP_ROLES, f"{workflow_path}.steps unknown role: {role}")
            _require(
                isinstance(slug, str) and slug.strip(),
                f"{workflow_path}.steps.{role} must be a non-empty string slug",
            )
            parsed_steps.append(WorkflowHintStep(role=role, slug=slug))

        raw_inputs = raw_workflow.get("inputs", {})
        _require(isinstance(raw_inputs, dict), f"{workflow_path}.inputs must be a mapping")
        inputs = {str(k): str(v) for k, v in raw_inputs.items()}

        raw_defaults = raw_workflow.get("defaults", {})
        _require(isinstance(raw_defaults, dict), f"{workflow_path}.defaults must be a mapping")
        defaults = dict(raw_defaults)
        workflows.append(
            WorkflowHint(
                name=name,
                pattern=pattern,
                steps=tuple(parsed_steps),
                inputs=inputs,
                defaults=defaults,
            )
        )

    return WorkflowHints(
        service_env_prefix=service_env_prefix,
        workflows=tuple(workflows),
    )
