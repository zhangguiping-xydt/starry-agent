from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_to_skill.skillgen.workflow_hints import (
    WorkflowHint,
    WorkflowHints,
)


def derive_service_env_prefix(project_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(project_name).strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").upper()
    return cleaned or "LOCAL_REPOSITORY"


def service_env_names(env_prefix: str) -> dict[str, str]:
    return {
        "env_prefix": env_prefix,
        "base_url_env": env_prefix + "_BASE_URL",
        "token_env": env_prefix + "_TOKEN",
    }


_READ_SAFE_METHODS = {"GET"}


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    env_prefix: str
    base_url_env: str
    token_env: str


@dataclass(frozen=True)
class WorkflowStep:
    role: str
    slug: str
    interface: dict[str, Any]
    module: str


@dataclass(frozen=True)
class WorkflowInput:
    name: str
    type: str
    maps_to: str
    required: bool


@dataclass(frozen=True)
class WorkflowPlan:
    name: str
    pattern: str
    intent: str
    inputs: tuple[WorkflowInput, ...]
    defaults: dict[str, Any]
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class TaskWorkflowPlan:
    target: Path
    analysis_root: Path
    scan: dict[str, Any]
    profile: dict[str, Any]
    callable_capabilities: dict[str, Any]
    service: ServiceConfig
    workflows: tuple[WorkflowPlan, ...]
    need_summary: str
    language: str = "en"


_WRITE_INTERFACE_TOKENS = (
    "save", "update", "delete", "create", "submit", "push",
    "writeback", "upload", "import",
)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _is_read_safe(interface: dict[str, Any]) -> bool:
    side_effects = str(interface.get("side_effects") or "unknown").lower()
    if side_effects == "write":
        return False
    method = str(interface.get("http_method") or "").upper()
    route = str(interface.get("route") or "").lower()
    handler = str(interface.get("handler_symbol") or "").lower()
    haystack = route + " " + handler
    if any(token in haystack for token in _WRITE_INTERFACE_TOKENS):
        return False
    if side_effects == "read":
        return True
    return method in _READ_SAFE_METHODS or any(
        token in haystack for token in ("query", "search", "get", "list", "count", "detail")
    )


def _load_callable_capabilities(analysis: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = analysis.expanduser().resolve()
    scan = _read_json(root / "scan.json")
    profile = _read_json(root / "profile.json")
    callable_capabilities = _read_json(root / "callable_capabilities.json")
    return scan, profile, callable_capabilities


def _interface_index(callable_capabilities: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(interface.get("slug")): interface
        for interface in callable_capabilities.get("interfaces") or []
        if isinstance(interface, dict) and interface.get("slug")
    }


def _build_workflow(hint: WorkflowHint, interfaces_by_slug: dict[str, dict[str, Any]]) -> WorkflowPlan:
    if not hint.steps:
        raise ValueError(f"workflow '{hint.name}' must declare at least one step")

    resolved_steps: list[WorkflowStep] = []
    for hint_step in hint.steps:
        interface = interfaces_by_slug.get(hint_step.slug)
        if interface is None:
            raise ValueError(f"workflow step references unknown interface slug: {hint_step.slug}")
        if not _is_read_safe(interface):
            raise ValueError(
                f"workflow step references write interface: {hint_step.slug}"
            )
        module = hint_step.slug.replace("-", "_")
        resolved_steps.append(
            WorkflowStep(
                role=hint_step.role,
                slug=hint_step.slug,
                interface=interface,
                module=module,
            )
        )

    workflow_inputs: list[WorkflowInput] = []
    for cli_name, wire_name in hint.inputs.items():
        workflow_inputs.append(
            WorkflowInput(
                name=cli_name,
                type="string",
                maps_to=wire_name,
                required=False,
            )
        )

    return WorkflowPlan(
        name=hint.name,
        pattern=hint.pattern,
        intent=f"workflow {hint.name} ({hint.pattern})",
        inputs=tuple(workflow_inputs),
        defaults=dict(hint.defaults),
        steps=tuple(resolved_steps),
    )


def plan_task_workflow(
    target: Path,
    analysis: Path,
    *,
    hints: WorkflowHints | None,
    need_summary: str,
    language: str = "auto",
) -> TaskWorkflowPlan:
    target_root = target.expanduser().resolve()
    if not target_root.exists() or not target_root.is_dir():
        raise ValueError("target repository must be an existing directory")

    scan, profile, callable_capabilities = _load_callable_capabilities(analysis)

    if hints is None:
        raise ValueError(
            "cannot generate task-workflow: workflow hints are required in the first version"
        )

    interfaces_by_slug = _interface_index(callable_capabilities)
    workflows: list[WorkflowPlan] = []
    for hint in hints.workflows:
        workflows.append(_build_workflow(hint, interfaces_by_slug))

    if not workflows:
        raise ValueError(
            "cannot generate task-workflow: hints did not declare any workflows"
        )

    project_name = str(
        callable_capabilities.get("project") or profile.get("name") or "local-repository"
    )
    env_prefix = (
        hints.service_env_prefix
        if hints.service_env_prefix
        else derive_service_env_prefix(project_name)
    )
    names = service_env_names(env_prefix)
    service = ServiceConfig(
        name=project_name,
        env_prefix=env_prefix,
        base_url_env=names["base_url_env"],
        token_env=names["token_env"],
    )

    return TaskWorkflowPlan(
        target=target_root,
        analysis_root=analysis.expanduser().resolve(),
        scan=scan,
        profile=profile,
        callable_capabilities=callable_capabilities,
        service=service,
        workflows=tuple(workflows),
        need_summary=need_summary,
        language=language,
    )
