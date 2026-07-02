from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import yaml
from typer.testing import CliRunner

from repo_to_skill.cli import app
from repo_to_skill.models import FileRecord, ScanResult
from repo_to_skill.reverse.callable_capabilities import build_callable_capabilities
from repo_to_skill.skillgen.planner import plan_callable_skills
from repo_to_skill.skillgen.renderer import render_callable_skills
from repo_to_skill.skillgen.validator import validate_skill


# --------------------------------------------------------------------------- #
# Synthetic sources (mirror the TMS CalculateWorkLoad demo + an unresolved case)
# --------------------------------------------------------------------------- #

ASHX = """<%@ WebHandler Language="C#" Class="CalculateWorkLoad" %>
using System;
using System.Web;
using System.IO;
using Newtonsoft.Json;

public class CalculateWorkLoad : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        string body = new StreamReader(context.Request.InputStream).ReadToEnd();
        BillApplyModel model = JsonConvert.DeserializeObject<BillApplyModel>(body);
        BillApplyTimeLenth result = KQWorkDateBL.CalculateTimeLength(model);
        context.Response.Write(JsonConvert.SerializeObject(result));
    }

    public bool IsReusable { get { return false; } }
}
"""

CS_MODELS = """using System;

public class BillApplyModel
{
    public string EmployeeInfo { get; set; }
    public DateTime ApplyStartDateTime { get; set; }
    public DateTime ApplyEndDateTime { get; set; }
    public bool IsContainHoliday { get; set; }
    public int BillType { get; set; }
}

public class BillApplyTimeLenth
{
    public decimal TimeLenthUintDay { get; set; }
    public decimal TimeLenthUintHour { get; set; }
}

public class KQWorkDateBL
{
    public BillApplyTimeLenth CalculateTimeLength(BillApplyModel model)
    {
        return new BillApplyTimeLenth();
    }
}
"""

MYSTERY_ASHX = """<%@ WebHandler Language="C#" Class="MysteryHandler" %>
public class MysteryHandler : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        string body = new StreamReader(context.Request.InputStream).ReadToEnd();
        UnknownPayload model = JsonConvert.DeserializeObject<UnknownPayload>(body);
        context.Response.Write("ok");
    }
    public bool IsReusable { get { return false; } }
}
"""

# tokens a callable caller must never contain
_BANNED_SCRIPT_TOKENS = (
    "import requests",
    "subprocess",
    "socket",
    "http.client",
    "os.system",
    "os.popen",
    "shutil",
    "eval(",
    "exec(",
)


def _write_scan(root: Path, files: dict[str, tuple[str, str]]) -> ScanResult:
    records: list[FileRecord] = []
    for rel, (language, content) in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        records.append(
            FileRecord(
                path=rel,
                size=len(content.encode("utf-8")),
                line_count=content.count("\n"),
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                language=language,
                role="source",
            )
        )
    return ScanResult(root=str(root), files=records)


def _prepare(tmp_path: Path, files: dict[str, tuple[str, str]]) -> tuple[Path, Path]:
    """Build a repo + analysis run dir and return (target, analysis_root)."""
    repo = tmp_path / "repo"
    scan = _write_scan(repo, files)
    capabilities = build_callable_capabilities(scan, repo)

    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps(scan.model_dump()), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "tms-atm"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps(capabilities.model_dump()), encoding="utf-8"
    )
    return repo, analysis


def _load_main(script_path: Path):
    spec = importlib.util.spec_from_file_location(f"callable_{script_path.stem}", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #


def test_plan_callable_skills_reads_capability_artifact(tmp_path: Path) -> None:
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )

    plan = plan_callable_skills(repo, analysis)

    # the capability set carries its own detected project name (the repo dir)
    assert plan.project_name == "repo"
    assert len(plan.interfaces) == 1
    assert plan.interfaces[0]["slug"] == "calculate-work-load"


# --------------------------------------------------------------------------- #
# Renderer — resolved contract
# --------------------------------------------------------------------------- #


def test_render_callable_skill_resolved_contract(tmp_path: Path) -> None:
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )
    plan = plan_callable_skills(repo, analysis)

    output = tmp_path / "skill"
    packs = render_callable_skills(plan, output)

    assert len(packs) == 1
    pack = packs[0]
    assert pack.name == "calculate-work-load"

    # every required file is present
    assert (pack / "SKILL.md").exists()
    assert (pack / "manifest.yaml").exists()
    assert (pack / "tools" / "calculate_work_load.tool.yaml").exists()
    assert (pack / "references" / "capability-source.md").exists()
    script_path = pack / "scripts" / "call_calculate_work_load.py"
    assert script_path.exists()

    # manifest is valid YAML with the callable runtime/auth/safety contract
    manifest = yaml.safe_load((pack / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["kind"] == "callable-capability"
    assert manifest["runtime"]["requires_live_system"] is True
    assert manifest["runtime"]["transport"] == "http"
    assert manifest["runtime"]["method"] == "POST"
    endpoint_env = manifest["runtime"]["endpoint_env"]
    token_env = manifest["auth"]["token_env"]
    assert endpoint_env == "CALCULATE_WORK_LOAD_ENDPOINT"
    assert endpoint_env.endswith("_ENDPOINT")
    assert token_env.endswith("_TOKEN")
    assert manifest["auth"]["required"] is True
    assert manifest["auth"]["type"] == "bearer"
    assert manifest["safety"]["dry_run_default"] is True
    assert manifest["safety"]["network"] == "requires-explicit-endpoint"
    assert manifest["safety"]["dependency_install"] == "disabled"
    assert manifest["safety"]["target_repository_writes"] == "disabled"

    # tool.yaml invocation must agree with the manifest, schemas keep legacy spelling
    tool = yaml.safe_load(
        (pack / "tools" / "calculate_work_load.tool.yaml").read_text(encoding="utf-8")
    )
    assert tool["invocation"]["method"] == "POST"
    assert tool["invocation"]["endpoint_env"] == endpoint_env
    assert tool["invocation"]["auth"]["token_env"] == token_env
    assert "EmployeeInfo" in tool["input_schema"]["properties"]
    assert "TimeLenthUintDay" in tool["output_schema"]["properties"]  # typo preserved verbatim
    assert tool["mapping"]["input_model"] == "BillApplyModel"

    # script is valid Python and honest about safety
    source = script_path.read_text(encoding="utf-8")
    ast.parse(source)
    assert f'ENDPOINT_ENV = "{endpoint_env}"' in source
    assert f'TOKEN_ENV = "{token_env}"' in source
    assert "<redacted>" in source
    assert "urllib.request" in source
    assert "urllib.error" in source
    assert 'payload["EmployeeInfo"] = args.employee_info' in source
    for banned in _BANNED_SCRIPT_TOKENS:
        assert banned not in source, f"callable script must not contain {banned!r}"

    # no machine paths leak into any generated file
    for file in pack.rglob("*"):
        if file.is_file():
            text = file.read_text(encoding="utf-8")
            assert "/media/" not in text
            assert "/home/" not in text
            assert "/tmp/" not in text

    # the caller previews offline (no endpoint env, no --execute) and never sends
    main = _load_main(script_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main(
            [
                "--employee-info",
                "E1",
                "--apply-start-date-time",
                "2026-01-01",
                "--apply-end-date-time",
                "2026-01-02",
                "--is-contain-holiday",
                "false",
                "--bill-type",
                "1",
            ]
        )
    out = buffer.getvalue()
    assert rc == 0
    assert "[preview]" in out
    assert "EmployeeInfo" in out  # the body it would send mirrors the source field


def test_render_callable_skill_splits_path_params_in_tool_schema(tmp_path: Path) -> None:
    fastapi_src = """from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class TransferRequest(BaseModel):
    new_department: str
    effective_date: str


@app.post(\"/employees/{employee_id}/transfer\")
def transfer_employee(employee_id: int, payload: TransferRequest):
    return {\"id\": employee_id}
"""
    repo, analysis = _prepare(tmp_path, {"main.py": ("Python", fastapi_src)})
    plan = plan_callable_skills(repo, analysis)

    output = tmp_path / "skill"
    packs = render_callable_skills(plan, output)
    assert len(packs) == 1
    pack = packs[0]

    tool = yaml.safe_load(next((pack / "tools").glob("*.tool.yaml")).read_text(encoding="utf-8"))

    # path param must NOT appear in the JSON body schema...
    body_props = tool["input_schema"].get("properties", {})
    assert "employee_id" not in body_props
    assert "new_department" in body_props
    assert "effective_date" in body_props
    assert "employee_id" not in tool["input_schema"].get("required", [])

    # ...but it must surface in path_parameters so agents still see it.
    path_params = tool.get("path_parameters", {})
    assert "employee_id" in path_params
    assert path_params["employee_id"]["required"] is True


def test_tool_yaml_quotes_ambiguous_field_names(tmp_path: Path) -> None:
    interface = {
        "slug": "toggle-flags",
        "stack": "python",
        "framework": "fastapi",
        "http_method": "POST",
        "route": "/flags",
        "handler_symbol": "toggle_flags",
        "handler_path": "main.py",
        "business_method": "toggle_flags",
        "endpoint_env": "TOGGLE_FLAGS_ENDPOINT",
        "token_env": "TOGGLE_FLAGS_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": "ToggleFlagsRequest",
            "fields": [
                {"name": "on", "type": "boolean", "required": True},
                {"name": "no", "type": "string", "required": False},
            ],
            "unresolved": False,
            "notes": [],
        },
        "response": {
            "model_name": "ToggleFlagsResponse",
            "fields": [{"name": "off", "type": "boolean", "required": False}],
            "unresolved": False,
            "notes": [],
        },
    }
    repo = tmp_path / "repo"
    analysis = tmp_path / "analysis"
    repo.mkdir()
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "sample", "interfaces": [interface], "notes": []}), encoding="utf-8"
    )
    pack = render_callable_skills(plan_callable_skills(repo, analysis), tmp_path / "skill")[0]

    tool = yaml.safe_load(next((pack / "tools").glob("*.tool.yaml")).read_text(encoding="utf-8"))

    assert "on" in tool["input_schema"]["required"]
    assert "on" in tool["input_schema"]["properties"]
    assert "no" in tool["input_schema"]["properties"]
    assert "off" in tool["output_schema"]["properties"]


def test_body_field_name_can_match_path_parameter(tmp_path: Path) -> None:
    interface = {
        "slug": "update-employee",
        "stack": "python",
        "framework": "fastapi",
        "http_method": "POST",
        "route": "/employees/{employee_id}",
        "handler_symbol": "update_employee",
        "handler_path": "main.py",
        "business_method": "update_employee",
        "endpoint_env": "UPDATE_EMPLOYEE_ENDPOINT",
        "token_env": "UPDATE_EMPLOYEE_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": "UpdateEmployeeRequest",
            "fields": [
                {"name": "employee_id", "type": "integer", "required": True, "location": "path"},
                {"name": "employee_id", "type": "string", "required": True, "location": "body"},
                {"name": "name", "type": "string", "required": True, "location": "body"},
            ],
            "unresolved": False,
            "notes": [],
        },
        "response": {"model_name": "UpdateEmployeeResponse", "fields": [], "unresolved": False, "notes": []},
    }
    repo = tmp_path / "repo"
    analysis = tmp_path / "analysis"
    repo.mkdir()
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "sample", "interfaces": [interface], "notes": []}), encoding="utf-8"
    )

    pack = render_callable_skills(plan_callable_skills(repo, analysis), tmp_path / "skill")[0]
    tool = yaml.safe_load(next((pack / "tools").glob("*.tool.yaml")).read_text(encoding="utf-8"))

    assert "employee_id" in tool["path_parameters"]
    assert "employee_id" in tool["input_schema"]["properties"]
    assert "employee_id" in tool["input_schema"]["required"]
    assert "name" in tool["input_schema"]["properties"]


def test_callable_path_params_are_url_encoded(tmp_path: Path) -> None:
    fastapi_src = """from fastapi import FastAPI

app = FastAPI()

@app.get(\"/files/{file_id}\")
def get_file(file_id: str):
    return {\"id\": file_id}
"""
    repo, analysis = _prepare(tmp_path, {"main.py": ("Python", fastapi_src)})
    plan = plan_callable_skills(repo, analysis)
    pack = render_callable_skills(plan, tmp_path / "skill")[0]
    script_path = pack / "scripts" / "call_main_get_file.py"

    spec = importlib.util.spec_from_file_location("call_main_get_file", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    endpoint = module.resolve_endpoint("https://api.example/files/{file_id}", {"file_id": "A/B C?"})

    assert endpoint == "https://api.example/files/A%2FB%20C%3F"


def test_callable_query_params_are_appended_to_endpoint(tmp_path: Path) -> None:
    fastapi_src = """from fastapi import FastAPI

app = FastAPI()

@app.get(\"/search\")
def search(q: str, limit: int = 10):
    return {\"items\": []}
"""
    repo, analysis = _prepare(tmp_path, {"main.py": ("Python", fastapi_src)})
    plan = plan_callable_skills(repo, analysis)
    pack = render_callable_skills(plan, tmp_path / "skill")[0]
    script_path = pack / "scripts" / "call_main_search.py"

    spec = importlib.util.spec_from_file_location("call_main_search", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    endpoint = module.apply_query_params("https://api.example/search?existing=1", {"q": "a/b", "limit": 10})

    assert endpoint == "https://api.example/search?existing=1&q=a%2Fb&limit=10"
    tool = yaml.safe_load(next((pack / "tools").glob("*.tool.yaml")).read_text(encoding="utf-8"))
    assert tool["query_parameters"]["q"]["required"] is True
    assert tool["query_parameters"]["limit"]["required"] is False


def test_duplicate_wire_names_across_locations_get_distinct_cli_args(tmp_path: Path) -> None:
    interface = {
        "slug": "sync-value",
        "stack": "python",
        "framework": "fastapi",
        "http_method": "POST",
        "route": "/sync",
        "handler_symbol": "sync_value",
        "handler_path": "main.py",
        "business_method": "sync_value",
        "endpoint_env": "SYNC_VALUE_ENDPOINT",
        "token_env": "SYNC_VALUE_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": "SyncValueRequest",
            "fields": [
                {"name": "value", "type": "string", "required": True, "location": "query"},
                {"name": "value", "type": "string", "required": True, "location": "body"},
            ],
            "unresolved": False,
            "notes": [],
        },
        "response": {"model_name": "SyncValueResponse", "fields": [], "unresolved": False, "notes": []},
    }
    repo = tmp_path / "repo"
    analysis = tmp_path / "analysis"
    repo.mkdir()
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "sample", "interfaces": [interface], "notes": []}), encoding="utf-8"
    )
    pack = render_callable_skills(plan_callable_skills(repo, analysis), tmp_path / "skill")[0]
    main = _load_main(pack / "scripts" / "call_sync_value.py")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main(["--query-value", "from-query", "--body-value", "from-body"])

    out = buffer.getvalue()
    assert rc == 0
    assert "endpoint: <SYNC_VALUE_ENDPOINT>?value=from-query" in out
    assert '"value": "from-body"' in out


def test_location_prefixed_cli_args_do_not_collide_with_existing_field_names(tmp_path: Path) -> None:
    interface = {
        "slug": "sync-value-collision",
        "stack": "python",
        "framework": "fastapi",
        "http_method": "POST",
        "route": "/sync",
        "handler_symbol": "sync_value_collision",
        "handler_path": "main.py",
        "business_method": "sync_value_collision",
        "endpoint_env": "SYNC_VALUE_COLLISION_ENDPOINT",
        "token_env": "SYNC_VALUE_COLLISION_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": "SyncValueCollisionRequest",
            "fields": [
                {"name": "value", "type": "string", "required": True, "location": "query"},
                {"name": "value", "type": "string", "required": True, "location": "body"},
                {"name": "body-value", "type": "string", "required": True, "location": "body"},
            ],
            "unresolved": False,
            "notes": [],
        },
        "response": {"model_name": "SyncValueCollisionResponse", "fields": [], "unresolved": False, "notes": []},
    }
    repo = tmp_path / "repo"
    analysis = tmp_path / "analysis"
    repo.mkdir()
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "sample", "interfaces": [interface], "notes": []}), encoding="utf-8"
    )
    pack = render_callable_skills(plan_callable_skills(repo, analysis), tmp_path / "skill")[0]
    main = _load_main(pack / "scripts" / "call_sync_value_collision.py")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main([
            "--query-value",
            "from-query",
            "--body-value",
            "from-body",
            "--body-value-2",
            "literal-body-value",
        ])

    out = buffer.getvalue()
    assert rc == 0
    assert "endpoint: <SYNC_VALUE_COLLISION_ENDPOINT>?value=from-query" in out
    assert '"value": "from-body"' in out
    assert '"body-value": "literal-body-value"' in out


def test_callable_rejects_non_http_endpoint_on_execute(tmp_path: Path, monkeypatch) -> None:
    pack = _render_resolved_pack(tmp_path)
    script_path = pack / "scripts" / "call_calculate_work_load.py"
    main = _load_main(script_path)
    monkeypatch.setenv("CALCULATE_WORK_LOAD_ENDPOINT", "file:///etc/passwd")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main(
            [
                "--employee-info",
                "E1",
                "--apply-start-date-time",
                "2026-01-01",
                "--apply-end-date-time",
                "2026-01-02",
                "--is-contain-holiday",
                "false",
                "--bill-type",
                "1",
                "--execute",
            ]
        )

    assert rc == 1
    assert "endpoint must use http or https" in buffer.getvalue()


def test_optional_boolean_is_omitted_when_not_provided(tmp_path: Path) -> None:
    interface = {
        "slug": "list-items",
        "stack": "python",
        "framework": "fastapi",
        "http_method": "POST",
        "route": "/items",
        "handler_symbol": "list_items",
        "handler_path": "main.py",
        "business_method": "list_items",
        "endpoint_env": "LIST_ITEMS_ENDPOINT",
        "token_env": "LIST_ITEMS_TOKEN",
        "side_effects": "unknown",
        "request": {
            "model_name": "ListItemsRequest",
            "fields": [{"name": "includeDrafts", "type": "boolean", "required": False}],
            "unresolved": False,
            "notes": [],
        },
        "response": {"model_name": "ListItemsResponse", "fields": [], "unresolved": False, "notes": []},
    }
    analysis = tmp_path / "analysis"
    repo = tmp_path / "repo"
    repo.mkdir()
    analysis.mkdir()
    (analysis / "scan.json").write_text(json.dumps({"root": str(repo), "files": []}), encoding="utf-8")
    (analysis / "profile.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
    (analysis / "callable_capabilities.json").write_text(
        json.dumps({"project": "sample", "interfaces": [interface], "notes": []}), encoding="utf-8"
    )
    plan = plan_callable_skills(repo, analysis)
    pack = render_callable_skills(plan, tmp_path / "skill")[0]
    main = _load_main(pack / "scripts" / "call_list_items.py")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main([])

    assert rc == 0
    assert "body:     {}" in buffer.getvalue()


# --------------------------------------------------------------------------- #
# Renderer — unresolved contract degrades to a --json-body caller
# --------------------------------------------------------------------------- #


def test_render_callable_skill_unresolved_uses_json_body(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path, {"Mystery.ashx": ("ASP.NET", MYSTERY_ASHX)})
    plan = plan_callable_skills(repo, analysis)

    packs = render_callable_skills(plan, tmp_path / "skill")
    assert len(packs) == 1
    pack = packs[0]
    assert pack.name == "mystery-handler"

    script_path = pack / "scripts" / "call_mystery_handler.py"
    source = script_path.read_text(encoding="utf-8")
    ast.parse(source)
    assert "--json-body" in source
    assert "json.loads(args.json_body)" in source

    main = _load_main(script_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = main(["--json-body", "{}"])
    assert rc == 0
    assert "[preview]" in buffer.getvalue()


# --------------------------------------------------------------------------- #
# Renderer — one pack per interface, unique directories
# --------------------------------------------------------------------------- #


def test_render_callable_skills_one_pack_per_interface(tmp_path: Path) -> None:
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
            "Mystery.ashx": ("ASP.NET", MYSTERY_ASHX),
        },
    )
    plan = plan_callable_skills(repo, analysis)

    packs = render_callable_skills(plan, tmp_path / "skill")

    assert len(packs) == 2
    names = {pack.name for pack in packs}
    assert names == {"calculate-work-load", "mystery-handler"}


# --------------------------------------------------------------------------- #
# Validator — callable branch
# --------------------------------------------------------------------------- #


def _render_resolved_pack(tmp_path: Path) -> Path:
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )
    plan = plan_callable_skills(repo, analysis)
    packs = render_callable_skills(plan, tmp_path / "skill")
    return packs[0]


def test_validator_passes_on_rendered_callable_pack(tmp_path: Path) -> None:
    pack = _render_resolved_pack(tmp_path)
    report = validate_skill(pack)
    # urlopen(...) must NOT trip the bare open( ban, and urllib.request/error are allowed
    assert report.status == "PASS", report.findings


def test_validator_flags_dangerous_token_in_callable_script(tmp_path: Path) -> None:
    pack = _render_resolved_pack(tmp_path)
    script = pack / "scripts" / "call_calculate_work_load.py"
    script.write_text(script.read_text(encoding="utf-8") + "\nimport subprocess\n", encoding="utf-8")
    report = validate_skill(pack)
    assert report.status == "FAIL"
    assert any("subprocess" in finding for finding in report.findings)


def test_validator_flags_non_dry_run_default_manifest(tmp_path: Path) -> None:
    pack = _render_resolved_pack(tmp_path)
    manifest = pack / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "dry_run_default: true", "dry_run_default: false"
        ),
        encoding="utf-8",
    )
    report = validate_skill(pack)
    assert report.status == "FAIL"
    assert any("dry_run_default" in finding for finding in report.findings)


def test_validator_flags_env_mismatch_between_manifest_and_script(tmp_path: Path) -> None:
    pack = _render_resolved_pack(tmp_path)
    manifest = pack / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "CALCULATE_WORK_LOAD_TOKEN", "SOME_OTHER_TOKEN"
        ),
        encoding="utf-8",
    )
    report = validate_skill(pack)
    assert report.status == "FAIL"
    assert any("token_env" in finding.lower() or "TOKEN_ENV" in finding for finding in report.findings)


def test_validator_flags_hardcoded_endpoint_env_drop(tmp_path: Path) -> None:
    pack = _render_resolved_pack(tmp_path)
    manifest = pack / "manifest.yaml"
    # endpoint_env that no longer ends with _ENDPOINT must be rejected
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "endpoint_env: CALCULATE_WORK_LOAD_ENDPOINT",
            "endpoint_env: https://prod.internal/calc",
        ),
        encoding="utf-8",
    )
    report = validate_skill(pack)
    assert report.status == "FAIL"
    assert any("endpoint_env" in finding for finding in report.findings)


# --------------------------------------------------------------------------- #
# CLI — generate --mode callable
# --------------------------------------------------------------------------- #

runner = CliRunner()


def test_cli_generate_mode_callable_produces_validating_pack(tmp_path: Path) -> None:
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )
    output = tmp_path / "skill"
    result = runner.invoke(
        app,
        ["generate", str(repo), "--analysis", str(analysis), "--output", str(output), "--mode", "callable"],
    )
    assert result.exit_code == 0, result.stdout
    pack = output / "calculate-work-load"
    assert (pack / "manifest.yaml").is_file()
    assert validate_skill(pack).status == "PASS"


def test_cli_generate_mode_callable_reports_when_no_interfaces(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path, {"util.py": ("Python", "def add(a, b):\n    return a + b\n")})
    output = tmp_path / "skill"
    result = runner.invoke(
        app,
        ["generate", str(repo), "--analysis", str(analysis), "--output", str(output), "--mode", "callable"],
    )
    assert result.exit_code == 0, result.stdout
    assert "No callable HTTP interfaces were detected." in result.stdout
    assert "FastAPI" in result.stdout


def test_cli_generate_rejects_unknown_mode(tmp_path: Path) -> None:
    repo, analysis = _prepare(tmp_path, {"util.py": ("Python", "x = 1\n")})
    output = tmp_path / "skill"
    result = runner.invoke(
        app,
        ["generate", str(repo), "--analysis", str(analysis), "--output", str(output), "--mode", "bogus"],
    )
    assert result.exit_code == 1
    assert "Unknown mode" in result.stdout


def test_cli_generate_default_mode_is_repo_map(tmp_path: Path) -> None:
    # default mode must stay repo-map; callable artifacts are ignored without --mode callable
    repo, analysis = _prepare(
        tmp_path,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )
    output = tmp_path / "skill"
    result = runner.invoke(
        app,
        ["generate", str(repo), "--analysis", str(analysis), "--output", str(output)],
    )
    # repo-map generation needs the full analysis artifact set, which _prepare does
    # not write, so it must fail cleanly rather than silently emit a callable pack
    assert result.exit_code == 1
    assert not (output / "calculate-work-load").exists()
