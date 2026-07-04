from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FILES = (
    "manifest.yaml",
    "SKILL.md",
    "scripts/inspect_repo.py",
    "scripts/common.py",
    "references/project-map.md",
    "references/capability-graph.md",
    "references/skill-spec.md",
    "references/confidence-report.md",
)

DANGEROUS_SCRIPT_TOKENS = (
    "subprocess",
    "os.system",
    "os.popen",
    "shutil.rmtree",
    "shutil.move",
    "shutil.copy",
    "requests",
    "urllib",
    "socket",
    "http.client",
    "ftplib",
    "open(",
    "write_text",
    "write_bytes",
    "unlink",
    "os.remove",
    "os.unlink",
    "rename",
    "replace",
    "pip",
    "npm",
    "exec(",
    "eval(",
    "pty",
)

# A callable caller is the one place network access is allowed, and only through
# the urllib request/error submodules. Drop "urllib" (allowed) and "open(" (would
# match the legitimate "urlopen(") from the substring ban; genuine bare open() is
# caught separately by a word-boundary regex.
CALLABLE_DANGEROUS_SCRIPT_TOKENS = tuple(
    token for token in DANGEROUS_SCRIPT_TOKENS if token not in {"urllib", "open("}
)
ALLOWED_URLLIB_SUBMODULES = {"request", "error", "parse"}

READONLY_MANIFEST_BANNED_TOKENS = (
    "CapabilityRegistry",
    "FastAPI",
    "runtime hot registration",
    "hot registration",
    "multi-agent-dev",
    "vector database",
    "remote database",
)
# A callable manifest legitimately names its source framework (e.g. fastapi), so
# "FastAPI" must not be banned there.
CALLABLE_MANIFEST_BANNED_TOKENS = tuple(
    token for token in READONLY_MANIFEST_BANNED_TOKENS if token != "FastAPI"
)

REQUIRED_MANIFEST_SAFETY = {
    "read_only": True,
    "network": "disabled",
    "dependency_install": "disabled",
    "target_repository_writes": "disabled",
}

REQUIRED_CALLABLE_SAFETY = {
    "dry_run_default": True,
    "network": "requires-explicit-endpoint",
    "dependency_install": "disabled",
    "target_repository_writes": "disabled",
}

REQUIRED_TASK_WORKFLOW_SAFETY = {
    "dry_run_default": True,
    "network": "requires-explicit-endpoint",
    "dependency_install": "disabled",
    "target_repository_writes": "disabled",
}

MACHINE_PATH_PATTERNS = (
    re.compile(r"/media/"),
    re.compile(r"/home/"),
    re.compile(r"/tmp(?:/|\b)"),
)
CALLABLE_MACHINE_PATH_PATTERNS = MACHINE_PATH_PATTERNS + (
    re.compile(r"/Users/"),
    re.compile(r"[A-Za-z]:\\"),
)

CALLABLE_SCRIPT_SAFETY_MARKERS = (
    "ENDPOINT_ENV =",
    "TOKEN_ENV =",
    "<redacted>",
    "args.dry_run",
    "args.execute",
)


@dataclass(frozen=True)
class SkillValidationReport:
    status: str
    findings: list[str] = field(default_factory=list)


_SCRIPT_WRITE_MODE_RE = re.compile(r"open\s*\([^\n]*[\"'](?:w|a|x|\+)[\"']")
_BARE_OPEN_RE = re.compile(r"\bopen\s*\(")
_URLLIB_SUBMODULE_RE = re.compile(r"urllib\.(\w+)")
_STRING_CONST_RE = re.compile(r'^([A-Z_]+)\s*=\s*"([^"]*)"', re.MULTILINE)


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_yaml_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(_text(path))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- #
# Read-only repo-map branch (unchanged behavior)
# --------------------------------------------------------------------------- #


def _check_required_files(root: Path, findings: list[str]) -> None:
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            findings.append(f"missing required file: {relative}")


def _check_scripts(root: Path, findings: list[str]) -> None:
    for relative in ("scripts/inspect_repo.py", "scripts/common.py"):
        path = root / relative
        if not path.is_file():
            continue
        content = _text(path)
        for token in DANGEROUS_SCRIPT_TOKENS:
            if token in content:
                findings.append(f"dangerous token in {relative}: {token}")
        if _SCRIPT_WRITE_MODE_RE.search(content):
            findings.append(f"dangerous token in {relative}: writable open mode")


def _check_manifest(root: Path, findings: list[str]) -> None:
    path = root / "manifest.yaml"
    if not path.is_file():
        return
    content = _text(path)
    try:
        manifest = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        findings.append(f"invalid manifest.yaml: {exc}")
        return
    if not isinstance(manifest, dict):
        findings.append("invalid manifest.yaml: root must be a mapping")
        return
    for key in ("name", "description", "version", "source_project", "capabilities", "generated_by"):
        if key not in manifest:
            findings.append(f"manifest.yaml missing field: {key}")
    safety = manifest.get("safety")
    if not isinstance(safety, dict):
        findings.append("manifest.yaml missing safety boundary: safety")
    else:
        for key, expected in REQUIRED_MANIFEST_SAFETY.items():
            actual = safety.get(key)
            if actual != expected:
                findings.append(f"manifest.yaml safety.{key} must be {expected!r}")
    for token in READONLY_MANIFEST_BANNED_TOKENS:
        if token in content:
            findings.append(f"manifest.yaml contains runtime registration or remote dependency token: {token}")


def _check_machine_paths(root: Path, findings: list[str], *, include_all_skill_files: bool = False) -> None:
    if include_all_skill_files:
        patterns = CALLABLE_MACHINE_PATH_PATTERNS
        checked = [root / "SKILL.md", root / "manifest.yaml"]
        for sub in ("references", "tools", "scripts"):
            checked.extend(sorted((root / sub).glob("**/*")))
    else:
        patterns = MACHINE_PATH_PATTERNS
        checked = [root / "SKILL.md"] + sorted((root / "references").glob("**/*"))
    for path in checked:
        if not path.is_file():
            continue
        content = _text(path)
        for pattern in patterns:
            if pattern.search(content):
                findings.append(f"machine absolute path found in {path.relative_to(root)}: {pattern.pattern}")


def _validate_readonly(root: Path, findings: list[str]) -> None:
    _check_required_files(root, findings)
    _check_scripts(root, findings)
    _check_manifest(root, findings)
    _check_machine_paths(root, findings)


# --------------------------------------------------------------------------- #
# Callable-capability branch
# --------------------------------------------------------------------------- #


def _check_callable_required_files(root: Path, findings: list[str]) -> None:
    for relative in ("manifest.yaml", "SKILL.md", "references/capability-source.md"):
        if not (root / relative).is_file():
            findings.append(f"missing required file: {relative}")
    tools = sorted((root / "tools").glob("*.tool.yaml"))
    if len(tools) != 1:
        findings.append(f"callable pack must contain exactly one tools/*.tool.yaml (found {len(tools)})")
    scripts = sorted((root / "scripts").glob("call_*.py"))
    if len(scripts) != 1:
        findings.append(f"callable pack must contain exactly one scripts/call_*.py (found {len(scripts)})")


def _check_callable_bundle_required_files(root: Path, findings: list[str]) -> None:
    for relative in (
        "manifest.yaml",
        "SKILL.md",
        "references/capability-selection.md",
        "references/capability-source.md",
    ):
        if not (root / relative).is_file():
            findings.append(f"missing required file: {relative}")
    tools = sorted((root / "tools").glob("*.tool.yaml"))
    scripts = sorted((root / "scripts").glob("call_*.py"))
    if not tools:
        findings.append("callable bundle must contain at least one tools/*.tool.yaml")
    if not scripts:
        findings.append("callable bundle must contain at least one scripts/call_*.py")
    if tools and scripts and len(tools) != len(scripts):
        findings.append(f"callable bundle tools/scripts count mismatch ({len(tools)} tools, {len(scripts)} scripts)")


def _check_callable_manifest(root: Path, findings: list[str]) -> dict[str, Any]:
    """Validate the callable manifest and return the values needed for consistency."""
    path = root / "manifest.yaml"
    manifest = _load_yaml_mapping(path)
    if manifest is None:
        findings.append("invalid manifest.yaml: root must be a mapping")
        return {}

    content = _text(path)
    for key in ("name", "version", "summary", "generated_by"):
        if key not in manifest:
            findings.append(f"manifest.yaml missing field: {key}")
    if manifest.get("kind") != "callable-capability":
        findings.append("manifest.yaml kind must be 'callable-capability'")

    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    if runtime.get("requires_live_system") is not True:
        findings.append("manifest.yaml runtime.requires_live_system must be true")
    if runtime.get("transport") != "http":
        findings.append("manifest.yaml runtime.transport must be 'http'")
    method = str(runtime.get("method") or "").strip()
    if not method:
        findings.append("manifest.yaml runtime.method must be set")
    endpoint_env = str(runtime.get("endpoint_env") or "").strip()
    if not endpoint_env or not endpoint_env.endswith("_ENDPOINT"):
        findings.append("manifest.yaml runtime.endpoint_env must be set and end with _ENDPOINT")

    auth = manifest.get("auth") if isinstance(manifest.get("auth"), dict) else {}
    if auth.get("required") is not True:
        findings.append("manifest.yaml auth.required must be true")
    if auth.get("type") != "bearer":
        findings.append("manifest.yaml auth.type must be 'bearer'")
    token_env = str(auth.get("token_env") or "").strip()
    if not token_env or not token_env.endswith("_TOKEN"):
        findings.append("manifest.yaml auth.token_env must be set and end with _TOKEN")

    safety = manifest.get("safety")
    if not isinstance(safety, dict):
        findings.append("manifest.yaml missing safety boundary: safety")
    else:
        for key, expected in REQUIRED_CALLABLE_SAFETY.items():
            if safety.get(key) != expected:
                findings.append(f"manifest.yaml safety.{key} must be {expected!r}")

    for token in CALLABLE_MANIFEST_BANNED_TOKENS:
        if token in content:
            findings.append(f"manifest.yaml contains forbidden token: {token}")

    return {"method": method, "endpoint_env": endpoint_env, "token_env": token_env}


def _check_callable_bundle_manifest(root: Path, findings: list[str]) -> dict[str, Any]:
    path = root / "manifest.yaml"
    manifest = _load_yaml_mapping(path)
    if manifest is None:
        findings.append("invalid manifest.yaml: root must be a mapping")
        return {}

    content = _text(path)
    for key in ("name", "version", "summary", "generated_by"):
        if key not in manifest:
            findings.append(f"manifest.yaml missing field: {key}")
    if manifest.get("kind") != "callable-bundle":
        findings.append("manifest.yaml kind must be 'callable-bundle'")

    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    if runtime.get("requires_live_system") is not True:
        findings.append("manifest.yaml runtime.requires_live_system must be true")
    if runtime.get("transport") != "http":
        findings.append("manifest.yaml runtime.transport must be 'http'")
    if not isinstance(runtime.get("interfaces_count"), int) or runtime.get("interfaces_count", 0) < 1:
        findings.append("manifest.yaml runtime.interfaces_count must be a positive integer")

    auth = manifest.get("auth") if isinstance(manifest.get("auth"), dict) else {}
    if auth.get("required") is not True:
        findings.append("manifest.yaml auth.required must be true")
    if auth.get("type") != "bearer":
        findings.append("manifest.yaml auth.type must be 'bearer'")

    safety = manifest.get("safety")
    if not isinstance(safety, dict):
        findings.append("manifest.yaml missing safety boundary: safety")
    else:
        for key, expected in REQUIRED_CALLABLE_SAFETY.items():
            if safety.get(key) != expected:
                findings.append(f"manifest.yaml safety.{key} must be {expected!r}")

    selection = manifest.get("selection") if isinstance(manifest.get("selection"), dict) else {}
    if not str(selection.get("need_summary") or "").strip():
        findings.append("manifest.yaml selection.need_summary must be set")
    if not str(selection.get("source") or "").strip():
        findings.append("manifest.yaml selection.source must be set")
    interfaces = selection.get("interfaces") if isinstance(selection.get("interfaces"), list) else []
    if not interfaces:
        findings.append("manifest.yaml selection.interfaces must contain at least one interface")

    for token in CALLABLE_MANIFEST_BANNED_TOKENS:
        if token in content:
            findings.append(f"manifest.yaml contains forbidden token: {token}")

    return manifest


def _check_callable_tool(root: Path, findings: list[str], manifest: dict[str, Any]) -> None:
    tools = sorted((root / "tools").glob("*.tool.yaml"))
    if len(tools) != 1:
        return
    tool = _load_yaml_mapping(tools[0])
    rel = tools[0].relative_to(root)
    if tool is None:
        findings.append(f"invalid {rel}: root must be a mapping")
        return
    invocation = tool.get("invocation") if isinstance(tool.get("invocation"), dict) else {}
    if invocation.get("transport") != "http":
        findings.append(f"{rel} invocation.transport must be 'http'")
    if manifest.get("method") and invocation.get("method") != manifest["method"]:
        findings.append(f"{rel} invocation.method must match manifest runtime.method")
    if manifest.get("endpoint_env") and invocation.get("endpoint_env") != manifest["endpoint_env"]:
        findings.append(f"{rel} invocation.endpoint_env must match manifest runtime.endpoint_env")
    auth = invocation.get("auth") if isinstance(invocation.get("auth"), dict) else {}
    if manifest.get("token_env") and auth.get("token_env") != manifest["token_env"]:
        findings.append(f"{rel} invocation.auth.token_env must match manifest auth.token_env")


def _check_callable_script_file(root: Path, path: Path, findings: list[str]) -> dict[str, str]:
    rel = path.relative_to(root)
    content = _text(path)

    for token in CALLABLE_DANGEROUS_SCRIPT_TOKENS:
        if token in content:
            findings.append(f"dangerous token in {rel}: {token}")
    if _BARE_OPEN_RE.search(content):
        findings.append(f"dangerous token in {rel}: bare open(")
    if _SCRIPT_WRITE_MODE_RE.search(content):
        findings.append(f"dangerous token in {rel}: writable open mode")
    for submodule in sorted(set(_URLLIB_SUBMODULE_RE.findall(content))):
        if submodule not in ALLOWED_URLLIB_SUBMODULES:
            findings.append(f"dangerous token in {rel}: urllib.{submodule}")

    for marker in CALLABLE_SCRIPT_SAFETY_MARKERS:
        if marker not in content:
            findings.append(f"{rel} missing safety marker: {marker}")

    return dict(_STRING_CONST_RE.findall(content))


def _check_callable_script(root: Path, findings: list[str], manifest: dict[str, Any]) -> None:
    scripts = sorted((root / "scripts").glob("call_*.py"))
    if len(scripts) != 1:
        return
    path = scripts[0]
    rel = path.relative_to(root)
    constants = _check_callable_script_file(root, path, findings)
    if manifest.get("endpoint_env") and constants.get("ENDPOINT_ENV") != manifest["endpoint_env"]:
        findings.append(f"{rel} ENDPOINT_ENV must match manifest runtime.endpoint_env")
    if manifest.get("token_env") and constants.get("TOKEN_ENV") != manifest["token_env"]:
        findings.append(f"{rel} TOKEN_ENV must match manifest auth.token_env")


def _validate_callable(root: Path, findings: list[str]) -> None:
    _check_callable_required_files(root, findings)
    manifest = _check_callable_manifest(root, findings)
    _check_callable_tool(root, findings, manifest)
    _check_callable_script(root, findings, manifest)
    _check_machine_paths(root, findings, include_all_skill_files=True)


def _tool_invocations(root: Path, findings: list[str]) -> list[dict[str, str]]:
    invocations: list[dict[str, str]] = []
    for path in sorted((root / "tools").glob("*.tool.yaml")):
        rel = path.relative_to(root)
        tool = _load_yaml_mapping(path)
        if tool is None:
            findings.append(f"invalid {rel}: root must be a mapping")
            continue
        invocation = tool.get("invocation") if isinstance(tool.get("invocation"), dict) else {}
        if invocation.get("transport") != "http":
            findings.append(f"{rel} invocation.transport must be 'http'")
        method = str(invocation.get("method") or "").strip()
        if not method:
            findings.append(f"{rel} invocation.method must be set")
        endpoint_env = str(invocation.get("endpoint_env") or "").strip()
        if not endpoint_env or not endpoint_env.endswith("_ENDPOINT"):
            findings.append(f"{rel} invocation.endpoint_env must be set and end with _ENDPOINT")
        auth = invocation.get("auth") if isinstance(invocation.get("auth"), dict) else {}
        token_env = str(auth.get("token_env") or "").strip()
        if not token_env or not token_env.endswith("_TOKEN"):
            findings.append(f"{rel} invocation.auth.token_env must be set and end with _TOKEN")
        invocations.append({"tool": str(rel), "endpoint_env": endpoint_env, "token_env": token_env})
    return invocations


def _script_constants(root: Path, findings: list[str]) -> list[dict[str, str]]:
    constants: list[dict[str, str]] = []
    for path in sorted((root / "scripts").glob("call_*.py")):
        values = _check_callable_script_file(root, path, findings)
        values["script"] = str(path.relative_to(root))
        constants.append(values)
    return constants


def _check_callable_bundle_consistency(root: Path, findings: list[str]) -> None:
    invocations = _tool_invocations(root, findings)
    scripts = _script_constants(root, findings)
    script_pairs = {
        (values.get("ENDPOINT_ENV", ""), values.get("TOKEN_ENV", ""))
        for values in scripts
    }
    for invocation in invocations:
        pair = (invocation["endpoint_env"], invocation["token_env"])
        if pair not in script_pairs:
            findings.append(
                f"{invocation['tool']} invocation envs must match one scripts/call_*.py constants"
            )


def _validate_callable_bundle(root: Path, findings: list[str]) -> None:
    _check_callable_bundle_required_files(root, findings)
    _check_callable_bundle_manifest(root, findings)
    _check_callable_bundle_consistency(root, findings)
    _check_machine_paths(root, findings, include_all_skill_files=True)


def _check_composite_required_files(root: Path, findings: list[str]) -> None:
    for relative in (
        "manifest.yaml",
        "SKILL.md",
        "orchestrator.py",
        "references/composition.md",
        "references/capability-source.md",
    ):
        if not (root / relative).is_file():
            findings.append(f"missing required file: {relative}")
    tools = sorted((root / "tools").glob("*.tool.yaml"))
    scripts = sorted((root / "scripts").glob("call_*.py"))
    if len(tools) < 2:
        findings.append(
            f"callable composite must contain at least 2 tools/*.tool.yaml (found {len(tools)})"
        )
    if len(scripts) < 2:
        findings.append(
            f"callable composite must contain at least 2 scripts/call_*.py (found {len(scripts)})"
        )
    if tools and scripts and len(tools) != len(scripts):
        findings.append(
            f"callable composite tools/scripts count mismatch ({len(tools)} tools, {len(scripts)} scripts)"
        )


def _check_composite_manifest(root: Path, findings: list[str]) -> dict[str, Any]:
    path = root / "manifest.yaml"
    manifest = _load_yaml_mapping(path)
    if manifest is None:
        findings.append("invalid manifest.yaml: root must be a mapping")
        return {}

    content = _text(path)
    for key in ("name", "version", "summary", "generated_by"):
        if key not in manifest:
            findings.append(f"manifest.yaml missing field: {key}")
    if manifest.get("kind") != "callable-composite":
        findings.append("manifest.yaml kind must be 'callable-composite'")

    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    if runtime.get("requires_live_system") is not True:
        findings.append("manifest.yaml runtime.requires_live_system must be true")
    if runtime.get("transport") != "http":
        findings.append("manifest.yaml runtime.transport must be 'http'")
    if not isinstance(runtime.get("interfaces_count"), int) or runtime.get("interfaces_count", 0) < 2:
        findings.append("manifest.yaml runtime.interfaces_count must be an integer >= 2")

    auth = manifest.get("auth") if isinstance(manifest.get("auth"), dict) else {}
    if auth.get("required") is not True:
        findings.append("manifest.yaml auth.required must be true")
    if auth.get("type") != "bearer":
        findings.append("manifest.yaml auth.type must be 'bearer'")

    safety = manifest.get("safety")
    if not isinstance(safety, dict):
        findings.append("manifest.yaml missing safety boundary: safety")
    else:
        for key, expected in REQUIRED_CALLABLE_SAFETY.items():
            if safety.get(key) != expected:
                findings.append(f"manifest.yaml safety.{key} must be {expected!r}")

    composition = manifest.get("composition") if isinstance(manifest.get("composition"), dict) else {}
    if not str(composition.get("goal") or "").strip():
        findings.append("manifest.yaml composition.goal must be set")
    if not str(composition.get("source") or "").strip():
        findings.append("manifest.yaml composition.source must be set")
    steps = composition.get("steps") if isinstance(composition.get("steps"), list) else []
    if len(steps) < 2:
        findings.append("manifest.yaml composition.steps must contain at least 2 entries")

    for token in CALLABLE_MANIFEST_BANNED_TOKENS:
        if token in content:
            findings.append(f"manifest.yaml contains forbidden token: {token}")

    return manifest


def _check_composite_orchestrator(root: Path, findings: list[str]) -> None:
    """Validate orchestrator.py: must ast-parse and must contain a TODO marker.

    The TODO marker is repo-to-skill's "field mapping not yet completed" signal
    to the generating agent. If it's been removed, the orchestrator is either
    incomplete (and someone forgot) or has been hand-edited past the
    deterministic scaffolding (which we still flag so reviewers notice).
    """
    path = root / "orchestrator.py"
    if not path.is_file():
        return  # already flagged by required-files check
    content = _text(path)
    try:
        ast.parse(content)
    except SyntaxError as exc:
        findings.append(f"orchestrator.py syntax error: {exc.msg} (line {exc.lineno})")
        return
    for token in CALLABLE_DANGEROUS_SCRIPT_TOKENS:
        if token in content:
            findings.append(f"dangerous token in orchestrator.py: {token}")
    if _BARE_OPEN_RE.search(content):
        findings.append("dangerous token in orchestrator.py: bare open(")
    if _SCRIPT_WRITE_MODE_RE.search(content):
        findings.append("dangerous token in orchestrator.py: writable open mode")
    if "# TODO: fill from step_" not in content:
        findings.append(
            "orchestrator.py missing '# TODO: fill from step_' marker; "
            "field mapping must be left as a TODO for the generating agent"
        )


def _validate_callable_composite(root: Path, findings: list[str]) -> None:
    _check_composite_required_files(root, findings)
    _check_composite_manifest(root, findings)
    # Reuse bundle consistency check for tool/script env alignment.
    _check_callable_bundle_consistency(root, findings)
    _check_composite_orchestrator(root, findings)
    _check_machine_paths(root, findings, include_all_skill_files=True)


# --------------------------------------------------------------------------- #
# Task-workflow branch
# --------------------------------------------------------------------------- #


def _check_task_workflow_required_files(root: Path, findings: list[str]) -> None:
    for relative in (
        "manifest.yaml",
        "SKILL.md",
        "references/workflow-source.md",
        "references/service-config.md",
    ):
        if not (root / relative).is_file():
            findings.append(f"missing required file: {relative}")
    if not list((root / "workflows").glob("*.yaml")):
        findings.append("task-workflow skill must contain at least one workflows/*.yaml")
    if not list((root / "scripts").glob("run_*.py")):
        findings.append("task-workflow skill must contain at least one scripts/run_*.py")
    if not list((root / "tools").glob("*.tool.yaml")):
        findings.append("task-workflow skill must contain at least one tools/*.tool.yaml")


def _check_task_workflow_manifest(root: Path, findings: list[str]) -> dict[str, Any]:
    manifest = _load_yaml_mapping(root / "manifest.yaml")
    if manifest is None:
        findings.append("invalid manifest.yaml: root must be a mapping")
        return {}

    for key in ("name", "version", "summary", "generated_by"):
        if key not in manifest:
            findings.append(f"manifest.yaml missing field: {key}")
    if manifest.get("kind") != "task-workflow":
        findings.append("manifest.yaml kind must be 'task-workflow'")

    service = manifest.get("service") if isinstance(manifest.get("service"), dict) else {}
    if not str(service.get("env_prefix") or "").strip():
        findings.append("manifest.yaml service.env_prefix must be set")
    if not str(service.get("base_url_env") or "").strip():
        findings.append("manifest.yaml service.base_url_env must be set")
    if not str(service.get("token_env") or "").strip():
        findings.append("manifest.yaml service.token_env must be set")

    safety = manifest.get("safety") if isinstance(manifest.get("safety"), dict) else {}
    for key, expected in REQUIRED_TASK_WORKFLOW_SAFETY.items():
        if safety.get(key) != expected:
            findings.append(f"manifest.yaml safety.{key} must be {expected!r}")

    interfaces = manifest.get("interfaces") if isinstance(manifest.get("interfaces"), list) else []
    for iface in interfaces:
        if not isinstance(iface, dict):
            findings.append("manifest.yaml interfaces entries must be mappings")
            continue
        side_effects = str(iface.get("side_effects") or "unknown").lower()
        if side_effects == "write":
            findings.append(
                f"manifest.yaml interface {iface.get('slug')} has side_effects=write; "
                "task-workflow must be read-only"
            )

    workflows = manifest.get("workflows") if isinstance(manifest.get("workflows"), list) else []
    if not workflows:
        findings.append("manifest.yaml workflows must contain at least one entry")
    for workflow in workflows:
        name_value = workflow.get("name") if isinstance(workflow, dict) else None
        file_value = workflow.get("file") if isinstance(workflow, dict) else None
        if (
            not isinstance(name_value, str)
            or not name_value.strip()
            or not isinstance(file_value, str)
            or not file_value.strip()
        ):
            findings.append("manifest.yaml workflow entries must have string name and file")
            continue
        if not (root / file_value).is_file():
            findings.append(f"manifest.yaml references missing workflow file: {file_value}")

    return manifest


_TASK_WORKFLOW_FORBIDDEN_TOKENS = (
    '"hardcoded-token"',
    "'hardcoded-token'",
    "Bearer hardcoded",
)


def _check_task_workflow_runners(root: Path, findings: list[str]) -> None:
    for runner in sorted((root / "scripts").glob("run_*.py")):
        content = _text(runner)
        rel = runner.relative_to(root)
        try:
            ast.parse(content)
        except SyntaxError as exc:
            findings.append(f"{rel} syntax error: {exc.msg} (line {exc.lineno})")
            continue
        for marker in ("BASE_URL_ENV =", "TOKEN_ENV ="):
            if marker not in content:
                findings.append(f"{rel} missing safety marker: {marker}")
        for token in _TASK_WORKFLOW_FORBIDDEN_TOKENS:
            if token in content:
                findings.append(f"{rel} contains hardcoded token: {token}")
        if "args.dry_run" not in content or "args.execute" not in content:
            findings.append(f"{rel} must respect --dry-run and --execute")
        if '"--execute"' not in content and "'--execute'" not in content:
            findings.append(f"{rel} must define an --execute flag")
        if '"--dry-run"' not in content and "'--dry-run'" not in content:
            findings.append(f"{rel} must define a --dry-run flag")


def _validate_task_workflow(root: Path, findings: list[str]) -> None:
    _check_task_workflow_required_files(root, findings)
    _check_task_workflow_manifest(root, findings)
    _check_task_workflow_runners(root, findings)
    _check_machine_paths(root, findings, include_all_skill_files=True)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def validate_skill(skill_path: Path) -> SkillValidationReport:
    root = skill_path.expanduser().resolve()
    findings: list[str] = []
    if not root.exists() or not root.is_dir():
        return SkillValidationReport(status="FAIL", findings=["skill path must be an existing directory"])

    manifest = _load_yaml_mapping(root / "manifest.yaml")
    kind = str((manifest or {}).get("kind") or "repo-map")

    if kind == "callable-capability":
        _validate_callable(root, findings)
    elif kind == "callable-bundle":
        _validate_callable_bundle(root, findings)
    elif kind == "callable-composite":
        _validate_callable_composite(root, findings)
    elif kind == "task-workflow":
        _validate_task_workflow(root, findings)
    else:
        _validate_readonly(root, findings)

    return SkillValidationReport(status="PASS" if not findings else "FAIL", findings=findings)
