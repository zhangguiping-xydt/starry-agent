from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from repo_to_skill.reverse.callable_capabilities import json_type_for
from repo_to_skill.skillgen.planner import (
    CallableBundlePlan,
    CallableCompositePlan,
    CallableSkillPlan,
    SkillPlan,
)
from repo_to_skill.skillgen.workflow_planner import TaskWorkflowPlan


_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"/media/[^\s)\]}>\"']*"),
    re.compile(r"/home/[^\s)\]}>\"']*"),
    re.compile(r"/tmp/[^\s)\]}>\"']*"),
    re.compile(r"/Users/[^\s)\]}>\"']*"),
    re.compile(r"[A-Za-z]:\\[^\s)\]}>\"']*"),
)
_CAPABILITY_BULLET_PATTERN = re.compile(r"(?m)^- ([a-z][a-z0-9_]*):")
_CAPABILITY_LABELS = {
    "architecture_modules": "architecture modules",
    "cli": "CLI",
    "configuration": "configuration",
    "database": "database scripts",
    "documentation": "documentation",
    "dotnet_project": ".NET project",
    "enterprise_modules": "architecture modules",
    "entrypoint": "entrypoints",
    "package_manager": "package manager",
    "release_scripts": "release scripts",
    "test": "tests",
    "web_app": "web application",
}


def _template_env() -> Environment:
    template_root = Path(__file__).resolve().parent / "templates"
    return Environment(
        loader=FileSystemLoader(template_root),
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    return cleaned or "local-repository"


def _strip_machine_paths(value: str) -> str:
    sanitized = value
    for pattern in _ABSOLUTE_PATH_PATTERNS:
        sanitized = pattern.sub("[local-path]", sanitized)
    return sanitized


def _inline_text(value: str, fallback: str = "") -> str:
    sanitized = _strip_machine_paths(str(value)).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized or fallback


def _inline_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_inline_text(str(value)) for value in values if _inline_text(str(value))]


def _sanitized_skill_spec(skill_spec: dict[str, Any], description: str) -> dict[str, Any]:
    sanitized = dict(skill_spec)
    sanitized["name"] = _inline_text(str(sanitized.get("name") or ""), "local-repository")
    sanitized["description"] = _inline_text(str(sanitized.get("description") or ""), description)
    sanitized["capabilities"] = _inline_list(sanitized.get("capabilities"))
    sanitized["safety_boundaries"] = _inline_list(sanitized.get("safety_boundaries"))
    sanitized["commands"] = _inline_list(sanitized.get("commands"))
    return sanitized


def _normalize_capability_labels(value: str) -> str:
    return _CAPABILITY_BULLET_PATTERN.sub(
        lambda match: f"- {_CAPABILITY_LABELS.get(match.group(1), match.group(1).replace('_', ' '))}:",
        value,
    )


def _list_items(profile: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in profile.get(key, [])]


def _summarize_list(values: list[str], limit: int = 40) -> dict[str, Any]:
    items = values[:limit]
    return {"paths": items, "total": len(values), "omitted": max(len(values) - len(items), 0)}


_FALLBACK_SIGNAL_PRIORITY = [
    "aspnet-web",
    "application-source",
    "database-scripts",
    "dotnet-project",
    "release-automation",
    "pipeline-config",
    "server-service",
    "client-app",
    "business-module",
]


def _fallback_module_signals(name: str, paths: list[str]) -> list[str]:
    lowered_name = name.rstrip("/").lower()
    lowered_paths = [path.lower() for path in paths]
    suffixes = {Path(path).suffix.lower() for path in paths}
    raw: set[str] = set()
    if lowered_name == "web" or suffixes & {".aspx", ".asmx", ".ashx", ".ascx"}:
        raw.add("aspnet-web")
    if lowered_name in {"db", "database", "sql"} or suffixes & {".sql", ".prc", ".vw", ".pck", ".seq"}:
        raw.add("database-scripts")
    if suffixes & {".sln", ".csproj"}:
        raw.add("dotnet-project")
    if paths and sum(1 for path in paths if Path(path).suffix.lower() not in {".md", ".rst", ".toml", ".yaml", ".yml", ".json", ".xml", ".config", ".resx", ".csproj", ".sln"}) >= max(1, len(paths) // 2):
        raw.add("application-source")
    if lowered_name in {"build", "deploy", "release"} or suffixes & {".bat", ".cmd"}:
        raw.add("release-automation")
    if "pipeline" in lowered_name or any("pipeline" in path for path in lowered_paths):
        raw.add("pipeline-config")
    if "server" in lowered_name or "service" in lowered_name:
        raw.add("server-service")
    if "client" in lowered_name or "ui" in lowered_name:
        raw.add("client-app")
    segmented_name = "_" in lowered_name and any(character.isdigit() for character in lowered_name)
    if segmented_name or "business" in lowered_name or "biz" in lowered_name or "manage" in lowered_name:
        raw.add("business-module")
    return [signal for signal in _FALLBACK_SIGNAL_PRIORITY if signal in raw]


def _fallback_module_summary(name: str, signals: list[str]) -> str:
    lowered_name = name.rstrip("/").lower()
    if lowered_name in {"build", "deploy", "release", "pipeline", "pipelines"}:
        return "Build, release, or deployment automation module."
    if "server-service" in signals:
        return "Server-side service or backend runtime module."
    if "client-app" in signals:
        return "Client application module inferred from module naming and file-type signals."
    if "aspnet-web" in signals:
        return "ASP.NET web application surface with pages, handlers, services, and configuration."
    if "application-source" in signals:
        return "Application source module inferred from dominant source files."
    if "database-scripts" in signals:
        return "Database schema and script layer with SQL objects or migration-like assets."
    if "business-module" in signals:
        return "Application or business capability module inferred from module naming."
    return ""


def _module_summary(profile: dict[str, Any]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for item in profile.get("module_summaries") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        modules.append(
            {
                "name": name,
                "total": int(item.get("total") or 0),
                "source": int(item.get("source") or 0),
                "configuration": int(item.get("configuration") or 0),
                "documentation": int(item.get("documentation") or 0),
                "test": int(item.get("test") or 0),
                "languages": [str(value) for value in item.get("languages") or []],
                "signals": [str(value) for value in item.get("signals") or []],
                "summary": str(item.get("summary") or ""),
                "representative_paths": [str(value) for value in item.get("representative_paths") or []],
            }
        )
    if modules:
        return sorted(modules, key=lambda item: (-item["total"], item["name"]))[:12]

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"source": 0, "configuration": 0, "documentation": 0, "test": 0})
    module_paths: dict[str, list[str]] = defaultdict(list)
    key_roles = {
        "source_files": "source",
        "configuration_files": "configuration",
        "documentation_files": "documentation",
        "test_files": "test",
    }
    for key, role in key_roles.items():
        for path in _list_items(profile, key):
            if "/" not in path:
                continue
            module = path.split("/", 1)[0] + "/"
            counts[module][role] += 1
            module_paths[module].append(path)
    for name, role_counts in counts.items():
        total = sum(role_counts.values())
        representative_paths = sorted(dict.fromkeys(module_paths[name]))[:6]
        signals = _fallback_module_signals(name, representative_paths)
        modules.append(
            {
                "name": name,
                "total": total,
                "summary": _fallback_module_summary(name, signals),
                "signals": signals,
                "languages": [],
                "representative_paths": representative_paths,
                **role_counts,
            }
        )
    return sorted(modules, key=lambda item: (-item["total"], item["name"]))[:12]


def _module_relationships(profile: dict[str, Any]) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    for item in profile.get("module_relationships") or []:
        if not isinstance(item, dict):
            continue
        source = _inline_text(str(item.get("source") or ""))
        target = _inline_text(str(item.get("target") or ""))
        relation = _inline_text(str(item.get("relation") or ""))
        if not source or not target or not relation:
            continue
        relationships.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "reason": _inline_text(str(item.get("reason") or "")),
                "evidence": _inline_list(item.get("evidence")),
            }
        )
    return sorted(relationships, key=lambda item: (item["source"], item["target"], item["relation"]))


def _task_entry_guide(profile: dict[str, Any]) -> list[dict[str, Any]]:
    guides: list[dict[str, Any]] = []
    for item in profile.get("task_entry_guide") or []:
        if not isinstance(item, dict):
            continue
        task = _inline_text(str(item.get("task") or ""))
        if not task:
            continue
        guides.append(
            {
                "task": task,
                "start_with": _inline_list(item.get("start_with")),
                "then_check": _inline_list(item.get("then_check")),
                "rationale": _inline_text(str(item.get("rationale") or "")),
            }
        )
    return sorted(guides, key=lambda item: item["task"])


def _validation_guide(profile: dict[str, Any]) -> list[dict[str, Any]]:
    guides: list[dict[str, Any]] = []
    for item in profile.get("validation_guide") or []:
        if not isinstance(item, dict):
            continue
        scope = _inline_text(str(item.get("scope") or ""))
        if not scope:
            continue
        guides.append(
            {
                "scope": scope,
                "commands": _inline_list(item.get("commands")),
                "paths": _inline_list(item.get("paths")),
                "notes": _inline_list(item.get("notes")),
            }
        )
    return sorted(guides, key=lambda item: item["scope"])


def _project_map(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "languages": _list_items(profile, "languages"),
        "ecosystems": _list_items(profile, "ecosystems"),
        "package_managers": _list_items(profile, "package_managers"),
        "entrypoints": _list_items(profile, "entrypoints"),
        "configuration_files": _summarize_list(_list_items(profile, "configuration_files")),
        "documentation_files": _summarize_list(_list_items(profile, "documentation_files")),
        "source_files": _summarize_list(_list_items(profile, "source_files")),
        "test_files": _summarize_list(_list_items(profile, "test_files")),
        "test_commands": _list_items(profile, "test_commands"),
        "run_commands": _list_items(profile, "run_commands"),
        "modules": _module_summary(profile),
        "module_relationships": _module_relationships(profile),
        "task_entry_guide": _task_entry_guide(profile),
        "validation_guide": _validation_guide(profile),
    }


def _capability_items(capability_graph: dict[str, Any], fallback_capabilities: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for node in capability_graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id") or "").removeprefix("capability:")
        label = _CAPABILITY_LABELS.get(raw_id, str(node.get("label") or raw_id.replace("_", " ")).strip())
        if raw_id or label:
            items.append({"id": raw_id or label.replace(" ", "_"), "label": label})
    if items:
        return sorted(items, key=lambda item: item["id"])
    return [
        {
            "id": capability.replace(" ", "_"),
            "label": _CAPABILITY_LABELS.get(capability.replace(" ", "_"), capability),
        }
        for capability in fallback_capabilities
    ]


def _key_paths(profile: dict[str, Any]) -> list[str]:
    modules = [module["name"] for module in _module_summary(profile)]
    if modules:
        return modules[:8]
    values: list[str] = []
    for key in ("configuration_files", "documentation_files", "source_files", "test_files"):
        for item in profile.get(key, []):
            path = str(item)
            values.append(path.split("/", 1)[0] + "/" if "/" in path else path)
    return sorted(dict.fromkeys(values))[:8]


def render_skill(plan: SkillPlan, output: Path) -> Path:
    """Render a reviewable AI coding agent skill pack directory from a SkillPlan."""
    output_root = output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "scripts").mkdir(exist_ok=True)
    (output_root / "references").mkdir(exist_ok=True)

    env = _template_env()
    capability_items = _capability_items(plan.capability_graph, plan.capabilities)
    display_project_name = _inline_text(plan.project_name, "local-repository")
    display_description = _inline_text(plan.description, "Local-first repository skill generated from static analysis.")
    sanitized_skill_spec = _sanitized_skill_spec(plan.skill_spec, display_description)
    context = {
        "skill_name": _safe_name(plan.project_name),
        "project_name": display_project_name,
        "description": display_description,
        "capabilities": plan.capabilities,
        "capability_items": capability_items,
        "scan": plan.scan,
        "profile": plan.profile,
        "capability_evidence": plan.capability_evidence,
        "capability_graph": plan.capability_graph,
        "skill_spec": sanitized_skill_spec,
        "verification_report": plan.verification_report,
        "confidence_report": _normalize_capability_labels(_strip_machine_paths(plan.confidence_report)),
        "project_map": _project_map(plan.profile),
        "key_paths": _key_paths(plan.profile),
        "generated_by": "repo-to-skill",
        "language": plan.language,
        "yaml_quote": _yaml_double_quoted,
    }

    outputs = {
        "manifest.yaml": "manifest.yaml.j2",
        "SKILL.md": "SKILL.md.j2",
        "scripts/inspect_repo.py": "scripts/inspect_repo.py.j2",
        "scripts/common.py": "scripts/common.py.j2",
        "references/project-map.md": "references/project-map.md.j2",
        "references/capability-graph.md": "references/capability-graph.md.j2",
        "references/skill-spec.md": "references/skill-spec.md.j2",
        "references/confidence-report.md": "references/confidence-report.md.j2",
    }

    for relative_path, template_name in outputs.items():
        rendered = env.get_template(template_name).render(**context)
        rendered = _strip_machine_paths(rendered)
        destination = output_root / relative_path
        destination.write_text(rendered, encoding="utf-8")

    return output_root


_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "array", "object"}
_METHOD_VERB = {
    "GET": "Read from",
    "POST": "Invoke",
    "PUT": "Update through",
    "PATCH": "Update through",
    "DELETE": "Delete through",
}


def _callable_kebab(value: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", spaced).strip("-").lower()
    return re.sub(r"-+", "-", cleaned)


def _python_identifier(value: str) -> str:
    ident = _callable_kebab(value).replace("-", "_")
    if not ident:
        return "value"
    if ident[0].isdigit():
        return f"v_{ident}"
    return ident


def _py_literal(value: str) -> str:
    """Sanitize a value for embedding inside a double-quoted Python/JSON string."""
    return _inline_text(value).replace("\\", "").replace('"', "'")


def _yaml_double_quoted(value: str) -> str:
    escaped = _inline_text(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _schema_type(raw_type: str) -> tuple[str, bool]:
    """Map a source type onto a JSON-schema type, flagging when it is a fallback."""
    kind = json_type_for(raw_type)
    if kind in _SCHEMA_TYPES:
        return kind, False
    return "string", True


def _callable_args(request: dict[str, Any]) -> list[dict[str, Any]]:
    args: list[dict[str, Any]] = []
    used: set[str] = set()
    for field in request.get("fields") or []:
        if not isinstance(field, dict):
            continue
        wire = _py_literal(str(field.get("name") or ""))
        if not wire:
            continue
        dest = _python_identifier(wire)
        if dest in used:
            continue
        used.add(dest)
        cli = "--" + _callable_kebab(wire)
        raw_type = _py_literal(str(field.get("type") or ""))
        schema_type, _ = _schema_type(str(field.get("type") or ""))
        required = bool(field.get("required"))
        location = str(field.get("location") or "body")
        help_text = _py_literal(f"{wire} ({raw_type or schema_type}, {location}).")
        pieces = [f'"{cli}"', f'dest="{dest}"']
        if required:
            pieces.append("required=True")
        if schema_type == "boolean":
            pieces.append("type=parse_bool")
            if not required:
                pieces.append("default=False")
        elif schema_type == "integer":
            pieces.append("type=int")
        elif schema_type == "number":
            pieces.append("type=float")
        pieces.append(f'help="{help_text}"')
        args.append(
            {
                "wire": wire,
                "dest": dest,
                "cli": cli,
                "required": required,
                "is_bool": schema_type == "boolean",
                "location": location,
                "add_argument": "parser.add_argument(" + ", ".join(pieces) + ")",
            }
        )
    return args


def _callable_schema_fields(contract: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    used: set[str] = set()
    for field in contract.get("fields") or []:
        if not isinstance(field, dict):
            continue
        wire = _py_literal(str(field.get("name") or ""))
        if not wire or wire in used:
            continue
        used.add(wire)
        raw_type = str(field.get("type") or "")
        schema_type, _ = _schema_type(raw_type)
        fields.append(
            {
                "wire": wire,
                "schema_type": schema_type,
                "required": bool(field.get("required")),
                "is_bool": schema_type == "boolean",
                "description": _inline_text(f"{wire} ({_inline_text(raw_type) or 'type unknown'})."),
            }
        )
    return fields


def _callable_sample_command(module: str, args: list[dict[str, Any]]) -> str:
    parts = [f"python scripts/call_{module}.py"]
    required_args = [arg for arg in args if arg["required"]]
    if required_args:
        for arg in required_args:
            placeholder = "false" if arg["is_bool"] else "<" + arg["dest"].upper() + ">"
            parts.append(f"{arg['cli']} {placeholder}")
    elif not args:
        parts.append("--json-body '{}'")
    return " \\\n  ".join(parts)


def _goal_intent(need_summary: str) -> str:
    """Turn a user goal into a 'you need to ...' clause for a skill trigger."""
    goal = (need_summary or "").strip().rstrip(".")
    if goal.lower() in {"", "selected callable interfaces"}:
        return "you need these live capabilities"
    return f"you need to {goal[0].lower()}{goal[1:]}"


def _bundle_skill_description(
    project_name: str, need_summary: str, interfaces_count: int, language: str = "en"
) -> str:
    """Trigger-shaped SKILL.md description: tells an agent WHEN to use the bundle."""
    if language == "zh-CN":
        return _inline_text(
            f"当你需要通过 {project_name} 系统的实时 HTTP API（{interfaces_count} 个 callable 工具）"
            f"完成“{need_summary}”，而不是重新实现逻辑时使用。"
        )
    tools_word = "tool" if interfaces_count == 1 else "tools"
    return _inline_text(
        f"Use when {_goal_intent(need_summary)} using the {project_name} system's live "
        f"HTTP APIs ({interfaces_count} callable {tools_word}) instead of reimplementing the logic."
    )


def _callable_skill_description(project_name: str, handler_symbol: str, http_method: str, route: str) -> str:
    """Trigger-shaped SKILL.md description for a single callable capability."""
    return _inline_text(
        f"Use when you need the live result of {project_name}'s {handler_symbol} "
        f"({http_method} {route}) — call the existing HTTP API instead of reimplementing the logic."
    )


def _callable_context(interface: dict[str, Any], project_name: str, slug: str, module: str) -> dict[str, Any]:
    request = interface.get("request") if isinstance(interface.get("request"), dict) else {}
    response = interface.get("response") if isinstance(interface.get("response"), dict) else {}
    http_method = _inline_text(str(interface.get("http_method") or "POST")).upper() or "POST"
    framework = _inline_text(str(interface.get("framework") or "http"))
    stack = _inline_text(str(interface.get("stack") or "unknown"))
    route = _inline_text(str(interface.get("route") or "/"))
    handler_symbol = _inline_text(str(interface.get("handler_symbol") or slug))
    handler_path = _inline_text(str(interface.get("handler_path") or ""))
    business_method = _inline_text(str(interface.get("business_method") or ""))
    endpoint_env = _inline_text(str(interface.get("endpoint_env") or "")) or f"{module.upper()}_ENDPOINT"
    token_env = _inline_text(str(interface.get("token_env") or "")) or f"{module.upper()}_TOKEN"
    side_effects = _inline_text(str(interface.get("side_effects") or "unknown")) or "unknown"

    args = _callable_args(request)
    path_args = [arg for arg in args if arg.get("location") == "path"]
    body_args = [arg for arg in args if arg.get("location") != "path"]
    request_fields = _callable_schema_fields(request)
    response_fields = _callable_schema_fields(response)
    # Split fields so tool.yaml exposes path params separately from the JSON
    # body schema. Otherwise agents read the body schema as including path
    # params (which the caller strips out before sending).
    path_field_names = {arg["wire"] for arg in path_args}
    request_body_fields = [field for field in request_fields if field["wire"] not in path_field_names]
    request_path_fields = [field for field in request_fields if field["wire"] in path_field_names]
    request_body_required = [field["wire"] for field in request_body_fields if field["required"]]
    request_path_required = [field["wire"] for field in request_path_fields if field["required"]]
    request_required = request_body_required

    verb = _METHOD_VERB.get(http_method, "Call")
    summary = _inline_text(f"{verb} the {framework} {http_method} interface {handler_symbol} of {project_name}.")
    description = _inline_text(
        f"Call the legacy {framework} {http_method} HTTP interface '{handler_symbol}' "
        f"(route {route}) exposed by the {project_name} repository. Argument names mirror the "
        "source models so the JSON contract stays faithful; field names are not renamed."
    )

    return {
        "project_name": project_name,
        "slug": slug,
        "module": module,
        "tool_name": module,
        "summary": summary,
        "description": description,
        "stack": stack,
        "framework": framework,
        "http_method": http_method,
        "route": route,
        "has_path_params": bool(path_args),
        "handler_symbol": handler_symbol,
        "handler_path": handler_path,
        "business_method": business_method,
        "skill_description": _callable_skill_description(project_name, handler_symbol, http_method, route),
        "endpoint_env": endpoint_env,
        "token_env": token_env,
        "side_effects": side_effects,
        "request_model": _inline_text(str(request.get("model_name") or "unknown")),
        "response_model": _inline_text(str(response.get("model_name") or "unknown")),
        "request_unresolved": bool(request.get("unresolved")),
        "response_unresolved": bool(response.get("unresolved")),
        "request_notes": _inline_list(request.get("notes")),
        "response_notes": _inline_list(response.get("notes")),
        "args": args,
        "path_args": path_args,
        "body_args": body_args,
        "has_args": bool(args),
        "has_body_args": bool(body_args),
        "request_fields": request_fields,
        "request_body_fields": request_body_fields,
        "request_path_fields": request_path_fields,
        "response_fields": response_fields,
        "request_required": request_required,
        "request_body_required": request_body_required,
        "request_path_required": request_path_required,
        "sample_command": _callable_sample_command(module, args),
        "generated_by": "repo-to-skill",
    }


def render_callable_skills(plan: CallableSkillPlan, output: Path) -> list[Path]:
    """Render one callable-capability skill pack per detected HTTP interface."""
    output_root = output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    env = _template_env()
    project_name = _inline_text(plan.project_name, "local-repository")
    created: list[Path] = []
    used_dirs: dict[str, int] = {}
    for interface in plan.interfaces:
        slug = _safe_name(str(interface.get("slug") or "interface"))
        count = used_dirs.get(slug, 0)
        used_dirs[slug] = count + 1
        if count:
            slug = f"{slug}-{count + 1}"
        module = _python_identifier(slug)
        context = _callable_context(interface, project_name, slug, module)
        context["language"] = plan.language
        context["yaml_quote"] = _yaml_double_quoted

        skill_root = output_root / slug
        (skill_root / "scripts").mkdir(parents=True, exist_ok=True)
        (skill_root / "tools").mkdir(parents=True, exist_ok=True)
        (skill_root / "references").mkdir(parents=True, exist_ok=True)

        outputs = {
            "SKILL.md": "callable/SKILL.md.j2",
            "manifest.yaml": "callable/manifest.yaml.j2",
            f"tools/{module}.tool.yaml": "callable/tools/tool.yaml.j2",
            "references/capability-source.md": "callable/references/capability-source.md.j2",
            f"scripts/call_{module}.py": "callable/scripts/call.py.j2",
        }
        for relative_path, template_name in outputs.items():
            rendered = env.get_template(template_name).render(**context)
            rendered = _strip_machine_paths(rendered)
            (skill_root / relative_path).write_text(rendered, encoding="utf-8")
        created.append(skill_root)

    return sorted(created)


def _bundle_context(plan: CallableBundlePlan) -> dict[str, Any]:
    project_name = _inline_text(plan.project_name, "local-repository")
    bundle_slug = _safe_name(plan.bundle_slug)
    interfaces: list[dict[str, Any]] = []
    used_modules: dict[str, int] = {}
    for item in plan.selection.items:
        raw_slug = _safe_name(str(item.interface.get("slug") or "interface"))
        count = used_modules.get(raw_slug, 0)
        used_modules[raw_slug] = count + 1
        slug = raw_slug if not count else f"{raw_slug}-{count + 1}"
        module = _python_identifier(slug)
        context = _callable_context(item.interface, project_name, slug, module)
        context["selection_score"] = item.score
        context["selection_reasons"] = [_inline_text(reason) for reason in item.reasons]
        context["language"] = plan.language
        interfaces.append(context)

    need_summary = _inline_text(plan.selection.need_summary, "Selected callable interfaces.")
    interfaces_count = len(interfaces)
    return {
        "project_name": project_name,
        "bundle_slug": bundle_slug,
        "need_summary": need_summary,
        "skill_description": _bundle_skill_description(project_name, need_summary, interfaces_count, plan.language),
        "selection_source": _inline_text(plan.selection.selection_source, "deterministic"),
        "interfaces": interfaces,
        "interfaces_count": interfaces_count,
        "generated_by": "repo-to-skill",
        "language": plan.language,
        "yaml_quote": _yaml_double_quoted,
    }


def render_callable_bundle(plan: CallableBundlePlan, output: Path) -> Path:
    """Render one goal-oriented callable-bundle skill containing multiple tools."""
    output_root = output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    env = _template_env()
    context = _bundle_context(plan)
    skill_root = output_root / context["bundle_slug"]
    (skill_root / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_root / "tools").mkdir(parents=True, exist_ok=True)
    (skill_root / "references").mkdir(parents=True, exist_ok=True)

    bundle_outputs = {
        "SKILL.md": "callable_bundle/SKILL.md.j2",
        "manifest.yaml": "callable_bundle/manifest.yaml.j2",
        "references/capability-selection.md": "callable_bundle/references/capability-selection.md.j2",
        "references/capability-source.md": "callable_bundle/references/capability-source.md.j2",
    }
    for relative_path, template_name in bundle_outputs.items():
        rendered = env.get_template(template_name).render(**context)
        rendered = _strip_machine_paths(rendered)
        (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    for interface in context["interfaces"]:
        outputs = {
            f"tools/{interface['module']}.tool.yaml": "callable/tools/tool.yaml.j2",
            f"scripts/call_{interface['module']}.py": "callable/scripts/call.py.j2",
        }
        for relative_path, template_name in outputs.items():
            rendered = env.get_template(template_name).render(**interface)
            rendered = _strip_machine_paths(rendered)
            (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    return skill_root


def _composite_skill_description(project_name: str, goal: str, steps_count: int) -> str:
    """Trigger-shaped SKILL.md description for a callable composite."""
    cleaned_goal = _inline_text(goal, "the requested business goal")
    return _inline_text(
        f"Use when you need the final business answer to '{cleaned_goal}' from the "
        f"{project_name} system by chaining its {steps_count} HTTP APIs in order, "
        f"instead of reimplementing the composition logic."
    )


def _composite_context(plan: CallableCompositePlan) -> dict[str, Any]:
    project_name = _inline_text(plan.project_name, "local-repository")
    composite_slug = _safe_name(plan.composite_slug)
    steps: list[dict[str, Any]] = []
    used_modules: dict[str, int] = {}
    for order_index, plan_step in enumerate(plan.steps):
        raw_slug = _safe_name(str(plan_step.interface.get("slug") or f"step-{order_index}"))
        count = used_modules.get(raw_slug, 0)
        used_modules[raw_slug] = count + 1
        slug = raw_slug if not count else f"{raw_slug}-{count + 1}"
        module = _python_identifier(slug)
        context = _callable_context(plan_step.interface, project_name, slug, module)
        context["order"] = plan_step.order
        context["selection_score"] = plan_step.score
        context["selection_reasons"] = [_inline_text(reason) for reason in plan_step.reasons]
        context["language"] = plan.language
        steps.append(context)

    goal = _inline_text(plan.goal, "requested business goal")
    steps_count = len(steps)
    return {
        "project_name": project_name,
        "composite_slug": composite_slug,
        "goal": goal,
        "steps": steps,
        "steps_count": steps_count,
        "skill_description": _composite_skill_description(project_name, goal, steps_count),
        "selection_source": _inline_text(plan.selection.selection_source, "deterministic"),
        "generated_by": "repo-to-skill",
        "language": plan.language,
        "yaml_quote": _yaml_double_quoted,
    }


def render_callable_composite(plan: CallableCompositePlan, output: Path) -> Path:
    """Render one ordered callable-composite skill (A->B->...)."""
    output_root = output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    env = _template_env()
    context = _composite_context(plan)
    skill_root = output_root / context["composite_slug"]
    (skill_root / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_root / "tools").mkdir(parents=True, exist_ok=True)
    (skill_root / "references").mkdir(parents=True, exist_ok=True)

    composite_outputs = {
        "SKILL.md": "callable_composite/SKILL.md.j2",
        "manifest.yaml": "callable_composite/manifest.yaml.j2",
        "orchestrator.py": "callable_composite/orchestrator.py.j2",
        "references/composition.md": "callable_composite/references/composition.md.j2",
        "references/capability-source.md": "callable_bundle/references/capability-source.md.j2",
    }
    for relative_path, template_name in composite_outputs.items():
        rendered = env.get_template(template_name).render(**context)
        rendered = _strip_machine_paths(rendered)
        (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    for step in context["steps"]:
        outputs = {
            f"tools/{step['module']}.tool.yaml": "callable/tools/tool.yaml.j2",
            f"scripts/call_{step['module']}.py": "callable/scripts/call.py.j2",
        }
        for relative_path, template_name in outputs.items():
            rendered = env.get_template(template_name).render(**step)
            rendered = _strip_machine_paths(rendered)
            (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    return skill_root


def _task_workflow_skill_description(
    project_name: str, need_summary: str, workflow_count: int, language: str = "en"
) -> str:
    if language == "zh-CN":
        return _inline_text(
            f"当你需要通过 {project_name} 系统的预定义 workflow（{workflow_count} 个）完成"
            f"“{need_summary}”而不是实时拼接 API 时使用。"
        )
    return _inline_text(
        f"Use when you need the {project_name} system's predefined workflows "
        f"({workflow_count}) to accomplish \"{need_summary}\" rather than "
        "improvising API chains at runtime."
    )


def _task_workflow_context(plan: TaskWorkflowPlan) -> dict[str, Any]:
    project_name = _inline_text(plan.project_name, "local-repository")
    bundle_slug = _safe_name(plan.need_summary or plan.project_name)

    interfaces: list[dict[str, Any]] = []
    used_modules: dict[str, int] = {}
    for workflow in plan.workflows:
        for step in workflow.steps:
            module = step.module
            count = used_modules.get(module, 0)
            used_modules[module] = count + 1
            slug = step.slug if not count else f"{step.slug}-{count + 1}"
            iface_context = _callable_context(step.interface, project_name, slug, module)
            iface_context["role"] = step.role
            iface_context["selection_score"] = 1.0
            iface_context["selection_reasons"] = []
            iface_context["language"] = plan.language
            interfaces.append(iface_context)

    workflows_context: list[dict[str, Any]] = []
    for workflow in plan.workflows:
        steps_context = []
        for step in workflow.steps:
            module = step.module
            matching = next(
                (iface for iface in interfaces if iface["module"] == module),
                None,
            )
            if matching is None:
                raise ValueError(
                    f"workflow {workflow.name} references unknown interface slug: {step.slug}"
                )
            steps_context.append({
                "role": step.role,
                "slug": step.slug,
                "interface": matching,
            })
        workflows_context.append({
            "name": workflow.name,
            "pattern": workflow.pattern,
            "intent": workflow.intent,
            "inputs": [
                {"name": i.name, "type": i.type, "maps_to": i.maps_to, "required": i.required}
                for i in workflow.inputs
            ],
            "defaults": dict(workflow.defaults),
            "steps": steps_context,
        })

    need_summary = _inline_text(plan.need_summary, "Run predefined task workflows.")
    return {
        "project_name": project_name,
        "bundle_slug": bundle_slug,
        "need_summary": need_summary,
        "service": {
            "name": plan.service.name,
            "env_prefix": plan.service.env_prefix,
            "base_url_env": plan.service.base_url_env,
            "token_env": plan.service.token_env,
        },
        "workflows": workflows_context,
        "interfaces": interfaces,
        "skill_description": _task_workflow_skill_description(
            project_name, need_summary, len(workflows_context), plan.language
        ),
        "generated_by": "repo-to-skill",
        "language": plan.language,
        "yaml_quote": _yaml_double_quoted,
    }


def render_task_workflow(plan: TaskWorkflowPlan, output: Path) -> Path:
    """Render one task-workflow skill directory."""
    output_root = output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    env = _template_env()
    context = _task_workflow_context(plan)
    skill_root = output_root / context["bundle_slug"]
    for sub in ("scripts", "tools", "references", "workflows"):
        (skill_root / sub).mkdir(parents=True, exist_ok=True)

    top_outputs = {
        "SKILL.md": "task_workflow/SKILL.md.j2",
        "manifest.yaml": "task_workflow/manifest.yaml.j2",
        "references/workflow-source.md": "task_workflow/references/workflow-source.md.j2",
        "references/service-config.md": "task_workflow/references/service-config.md.j2",
    }
    for relative_path, template_name in top_outputs.items():
        rendered = env.get_template(template_name).render(**context)
        rendered = _strip_machine_paths(rendered)
        (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    for workflow in context["workflows"]:
        workflow_context = dict(context)
        workflow_context["workflow"] = workflow
        rendered = env.get_template("task_workflow/workflow.yaml.j2").render(**workflow_context)
        rendered = _strip_machine_paths(rendered)
        (skill_root / "workflows" / f"{workflow['name']}.yaml").write_text(rendered, encoding="utf-8")

        runner_context = dict(context)
        runner_context["workflow"] = workflow
        rendered = env.get_template("task_workflow/scripts/run_workflow.py.j2").render(**runner_context)
        rendered = _strip_machine_paths(rendered)
        (skill_root / "scripts" / f"run_{workflow['name']}.py").write_text(rendered, encoding="utf-8")

    for interface in context["interfaces"]:
        for relative_path, template_name in (
            (f"tools/{interface['module']}.tool.yaml", "callable/tools/tool.yaml.j2"),
            (f"scripts/call_{interface['module']}.py", "callable/scripts/call.py.j2"),
        ):
            rendered = env.get_template(template_name).render(**interface)
            rendered = _strip_machine_paths(rendered)
            (skill_root / relative_path).write_text(rendered, encoding="utf-8")

    return skill_root
