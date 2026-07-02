from __future__ import annotations

import hashlib
from pathlib import Path

from repo_to_skill.models import FileRecord, ScanResult
from repo_to_skill.reverse.callable_capabilities import (
    build_callable_capabilities,
    json_type_for,
    _safe_read,
    _slugify,
)


def _write_scan(root: Path, files: dict[str, tuple[str, str]]) -> ScanResult:
    """Write ``{relpath: (language, content)}`` and build a metadata-only ScanResult."""
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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def test_slugify_splits_camel_and_pascal_case() -> None:
    assert _slugify("CalculateWorkLoad") == "calculate-work-load"
    assert _slugify("getUserByID") == "get-user-by-id"
    assert _slugify("Simple") == "simple"
    assert _slugify("") == "interface"


def test_json_type_for_maps_language_types() -> None:
    assert json_type_for("string") == "string"
    assert json_type_for("DateTime") == "string"
    assert json_type_for("int") == "integer"
    assert json_type_for("long") == "integer"
    assert json_type_for("decimal") == "number"
    assert json_type_for("bool") == "boolean"
    assert json_type_for("List<String>") == "array"
    assert json_type_for("int[]") == "array"
    assert json_type_for("Map<String, Object>") == "object"
    assert json_type_for("SomeCustomType") == "unknown"
    assert json_type_for("int?") == "integer"


def test_safe_read_rejects_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    assert _safe_read(root, "../outside.txt") == ""
    (root / "inside.txt").write_text("ok", encoding="utf-8")
    assert _safe_read(root, "inside.txt") == "ok"


# --------------------------------------------------------------------------- #
# .NET — IHttpHandler (.ashx), mirrors the TMS CalculateWorkLoad demo
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


def test_detects_ashx_handler_with_resolved_contract(tmp_path: Path) -> None:
    root = tmp_path / "tms"
    scan = _write_scan(
        root,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )

    result = build_callable_capabilities(scan, root)

    assert len(result.interfaces) == 1
    interface = result.interfaces[0]
    assert interface.stack == "dotnet"
    assert interface.framework == "asp.net-ihttphandler"
    assert interface.http_method == "POST"
    assert interface.slug == "calculate-work-load"
    assert interface.handler_path == "Handlers/CalculateWorkLoad.ashx"
    assert interface.business_method == "KQWorkDateBL.CalculateTimeLength"
    assert interface.endpoint_env == "CALCULATE_WORK_LOAD_ENDPOINT"
    assert interface.token_env == "CALCULATE_WORK_LOAD_TOKEN"

    request_names = {f.name for f in interface.request.fields}
    assert "EmployeeInfo" in request_names
    assert "ApplyStartDateTime" in request_names
    assert "IsContainHoliday" in request_names
    assert "BillType" in request_names
    assert interface.request.unresolved is False
    assert interface.request.model_name == "BillApplyModel"

    response_names = {f.name for f in interface.response.fields}
    assert "TimeLenthUintDay" in response_names
    assert "TimeLenthUintHour" in response_names
    assert interface.response.model_name == "BillApplyTimeLenth"

    # legacy field spellings must be preserved verbatim (wire contract alignment)
    day = next(f for f in interface.response.fields if f.name == "TimeLenthUintDay")
    assert day.type == "decimal"


def test_detects_ashx_business_method_from_local_service_variable(tmp_path: Path) -> None:
    handler = """<%@ WebHandler Language="C#" Class="CalculateWorkLoad" %>
using System.Web;
using Newtonsoft.Json;

public class CalculateWorkLoad : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        KQWorkDateBL kqWorkBll = new KQWorkDateBL();
        try
        {
            BillApplyModel billmodel = JsonConvert.DeserializeObject<BillApplyModel>("{}");
            BillApplyTimeLenth BillTimeLength = kqWorkBll.CalculateTimeLength(billmodel);
            context.Response.Write(JsonConvert.SerializeObject(BillTimeLength));
        }
        catch (Exception e)
        {
            WriteSystemErrorLog.WriteErrLog(e);
        }
    }

    public bool IsReusable { get { return false; } }
}
"""
    root = tmp_path / "tms"
    scan = _write_scan(
        root,
        {
            "Handlers/CalculateWorkLoad.ashx": ("ASP.NET", handler),
            "BLL/KQWorkDate.cs": ("C#", CS_MODELS),
        },
    )

    result = build_callable_capabilities(scan, root)

    assert len(result.interfaces) == 1
    interface = result.interfaces[0]
    assert interface.business_method == "KQWorkDateBL.CalculateTimeLength"
    assert interface.response.model_name == "BillApplyTimeLenth"


def test_unresolvable_request_type_degrades_to_todo(tmp_path: Path) -> None:
    handler = """<%@ WebHandler Language="C#" Class="MysteryHandler" %>
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
    root = tmp_path / "app"
    scan = _write_scan(root, {"Mystery.ashx": ("ASP.NET", handler)})

    result = build_callable_capabilities(scan, root)

    assert len(result.interfaces) == 1
    interface = result.interfaces[0]
    assert interface.http_method == "POST"
    assert interface.request.unresolved is True
    assert interface.request.fields == []
    assert any("TODO" in note for note in interface.request.notes)


# --------------------------------------------------------------------------- #
# Java — Spring @RestController
# --------------------------------------------------------------------------- #

SPRING = """package com.example.api;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/work")
public class WorkController {

    @PostMapping("/calculate")
    public WorkResult calculate(@RequestBody WorkRequest request) {
        return service.calculate(request);
    }
}
"""

SPRING_MODELS = """package com.example.api;

public class WorkRequest {
    private String employeeInfo;
    private long billType;
    private boolean containHoliday;
}

public class WorkResult {
    private double days;
    private double hours;
}
"""


def test_detects_spring_post_with_request_body(tmp_path: Path) -> None:
    root = tmp_path / "spring"
    scan = _write_scan(
        root,
        {
            "src/WorkController.java": ("Java", SPRING),
            "src/WorkModels.java": ("Java", SPRING_MODELS),
        },
    )

    result = build_callable_capabilities(scan, root)

    spring = [i for i in result.interfaces if i.stack == "java"]
    assert len(spring) == 1
    interface = spring[0]
    assert interface.framework == "spring"
    assert interface.http_method == "POST"
    assert interface.route == "/api/work/calculate"
    assert interface.handler_symbol == "WorkController.calculate"
    request_names = {f.name for f in interface.request.fields}
    assert request_names == {"employeeInfo", "billType", "containHoliday"}
    assert interface.request.unresolved is False


def test_detects_spring_request_body_with_extra_annotations(tmp_path: Path) -> None:
    controller = """package com.example.api;

import org.springframework.web.bind.annotation.*;

@Controller
@RequestMapping("/srv/entry")
public class AncillaryStaffController {

    @RequestMapping(value = "/getAncillaryStaffDic", method = RequestMethod.POST)
    @ResponseBody
    public ServiceData getAncillaryStaffDic(
            @RequestHeader(value = "X-Emp-No") String empNo,
            @RequestBody@ApiParam(value = "query entity", required = true) AncillaryStaffInfoDTO dto) throws Exception {
        return service.getAncillaryStaffDic(dto);
    }

    @RequestMapping(value = "/postAncillaryStaffInfo", method = RequestMethod.POST)
    @ResponseBody
    public ServiceData postAncillaryStaffInfo(
            @RequestBody @Validated @ApiParam(value = "submit object") AncillaryStaffInfoParam param) throws Exception {
        return service.postAncillaryStaffInfo(param);
    }
}
"""
    models = """package com.example.api;

public class AncillaryStaffInfoDTO {
    private String dicId;
    private String langId;
}

public class AncillaryStaffInfoParam {
    private String salaryNumber;
    private String salPointId;
}
"""
    root = tmp_path / "spring"
    scan = _write_scan(
        root,
        {
            "src/AncillaryStaffController.java": ("Java", controller),
            "src/AncillaryStaffModels.java": ("Java", models),
        },
    )

    result = build_callable_capabilities(scan, root)

    interfaces = {interface.handler_symbol: interface for interface in result.interfaces}
    assert set(interfaces) == {
        "AncillaryStaffController.getAncillaryStaffDic",
        "AncillaryStaffController.postAncillaryStaffInfo",
    }
    assert {f.name for f in interfaces["AncillaryStaffController.getAncillaryStaffDic"].request.fields} == {
        "dicId",
        "langId",
    }
    assert {f.name for f in interfaces["AncillaryStaffController.postAncillaryStaffInfo"].request.fields} == {
        "salaryNumber",
        "salPointId",
    }


# --------------------------------------------------------------------------- #
# Python — FastAPI + Pydantic
# --------------------------------------------------------------------------- #

FASTAPI = """from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class WorkloadRequest(BaseModel):
    employee_info: str
    bill_type: int
    is_container_holiday: bool = False


class WorkloadResponse(BaseModel):
    days: float
    hours: float


@app.post("/workload", response_model=WorkloadResponse)
def compute_workload(payload: WorkloadRequest):
    return WorkloadResponse(days=1.0, hours=8.0)
"""


def test_detects_fastapi_route_with_pydantic_models(tmp_path: Path) -> None:
    root = tmp_path / "py"
    scan = _write_scan(root, {"main.py": ("Python", FASTAPI)})

    result = build_callable_capabilities(scan, root)

    fastapi = [i for i in result.interfaces if i.framework == "fastapi"]
    assert len(fastapi) == 1
    interface = fastapi[0]
    assert interface.http_method == "POST"
    assert interface.route == "/workload"
    assert interface.handler_symbol == "compute_workload"

    request_names = {f.name for f in interface.request.fields}
    assert request_names == {"employee_info", "bill_type", "is_container_holiday"}
    required = {f.name for f in interface.request.fields if f.required}
    assert "employee_info" in required
    assert "is_container_holiday" not in required  # has default → optional

    response_names = {f.name for f in interface.response.fields}
    assert response_names == {"days", "hours"}


FASTAPI_PATH_PARAM = """from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Employee(BaseModel):
    id: int
    name: str
    department: str


@app.get("/employees/{employee_id}", response_model=Employee)
def get_employee(employee_id: int):
    return Employee(id=employee_id, name="Alice", department="Eng")
"""


def test_detects_fastapi_path_param_as_request_field(tmp_path: Path) -> None:
    root = tmp_path / "py"
    scan = _write_scan(root, {"main.py": ("Python", FASTAPI_PATH_PARAM)})

    result = build_callable_capabilities(scan, root)

    fastapi = [i for i in result.interfaces if i.framework == "fastapi"]
    assert len(fastapi) == 1
    interface = fastapi[0]
    assert interface.http_method == "GET"
    assert interface.route == "/employees/{employee_id}"

    request_names = {f.name for f in interface.request.fields}
    assert "employee_id" in request_names
    employee_id = next(f for f in interface.request.fields if f.name == "employee_id")
    assert employee_id.location == "path"
    assert employee_id.required is True
    assert employee_id.type == "int"


FASTAPI_DICT_BODY = """from fastapi import FastAPI
from typing import Dict

app = FastAPI()


@app.post("/employees/{employee_id}/transfer")
def transfer_employee(employee_id: int, payload: dict):
    return {"id": employee_id}
"""


def test_detects_fastapi_dict_body_without_pydantic_model(tmp_path: Path) -> None:
    root = tmp_path / "py"
    scan = _write_scan(root, {"main.py": ("Python", FASTAPI_DICT_BODY)})

    result = build_callable_capabilities(scan, root)

    fastapi = [i for i in result.interfaces if i.framework == "fastapi"]
    assert len(fastapi) == 1
    interface = fastapi[0]
    assert interface.http_method == "POST"
    assert interface.route == "/employees/{employee_id}/transfer"

    # Path param is captured
    fields_by_name = {f.name: f for f in interface.request.fields}
    assert "employee_id" in fields_by_name
    assert fields_by_name["employee_id"].location == "path"

    # Body is unresolved (dict without Pydantic shape) but the interface is
    # still usable via --json-body.
    assert interface.request.unresolved is True
    assert any("dict" in note.lower() or "json-body" in note.lower() or "could not" in note.lower()
               for note in interface.request.notes)


FASTAPI_ANNOTATED_BODY = """from fastapi import FastAPI, Body
from typing import Annotated
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    qty: int


@app.post(\"/items/\")
def create_item(payload: Annotated[Item, Body()]):
    return payload
"""


def test_detects_fastapi_annotated_body_with_nested_parens(tmp_path: Path) -> None:
    root = tmp_path / "py"
    scan = _write_scan(root, {"main.py": ("Python", FASTAPI_ANNOTATED_BODY)})

    result = build_callable_capabilities(scan, root)

    fastapi = [i for i in result.interfaces if i.framework == "fastapi"]
    assert len(fastapi) == 1
    interface = fastapi[0]
    assert interface.http_method == "POST"
    assert interface.route == "/items/"
    assert interface.handler_symbol == "create_item"
    request_names = {f.name for f in interface.request.fields}
    assert request_names == {"name", "qty"}
    assert interface.request.unresolved is False
    assert interface.request.model_name == "Item"


FASTAPI_QUERY_DEFAULT_PARENS = """from fastapi import FastAPI, Query

app = FastAPI()


@app.get(\"/search\")
def search(q: str = Query(\"default\")):
    return {\"q\": q}
"""


def test_detects_fastapi_handler_with_default_call_parens(tmp_path: Path) -> None:
    root = tmp_path / "py"
    scan = _write_scan(root, {"main.py": ("Python", FASTAPI_QUERY_DEFAULT_PARENS)})

    result = build_callable_capabilities(scan, root)

    fastapi = [i for i in result.interfaces if i.framework == "fastapi"]
    assert len(fastapi) == 1
    interface = fastapi[0]
    assert interface.handler_symbol == "search"
    assert interface.route == "/search"


def test_fastapi_scalar_params_are_query_fields(tmp_path: Path) -> None:
    source = """from fastapi import FastAPI

app = FastAPI()

@app.get(\"/search\")
def search(q: str, limit: int = 10):
    return {\"items\": []}
"""
    scan = _write_scan(tmp_path / "repo", {"main.py": ("Python", source)})

    capabilities = build_callable_capabilities(scan, tmp_path / "repo")

    interface = capabilities.interfaces[0]
    fields = {field.name: field for field in interface.request.fields}
    assert fields["q"].location == "query"
    assert fields["q"].required is True
    assert fields["limit"].location == "query"
    assert fields["limit"].required is False


def test_fastapi_skips_framework_context_params_and_preserves_required_query(tmp_path: Path) -> None:
    source = """from fastapi import FastAPI, Query, Request

app = FastAPI()

@app.get(\"/search\")
def search(request: Request, q: str = Query(...), limit: int = 10):
    return {\"items\": []}
"""
    scan = _write_scan(tmp_path / "repo", {"main.py": ("Python", source)})

    capabilities = build_callable_capabilities(scan, tmp_path / "repo")

    fields = {field.name: field for field in capabilities.interfaces[0].request.fields}
    assert "request" not in fields
    assert fields["q"].location == "query"
    assert fields["q"].required is True
    assert fields["limit"].location == "query"
    assert fields["limit"].required is False


def test_fastapi_required_sentinel_marks_query_required(tmp_path: Path) -> None:
    source = """from fastapi import FastAPI, Query
from pydantic.fields import Required

app = FastAPI()

@app.get(\"/search\")
def search(q: str = Query(Required), name: str = Query(default=Required)):
    return {\"items\": []}
"""
    scan = _write_scan(tmp_path / "repo", {"main.py": ("Python", source)})

    capabilities = build_callable_capabilities(scan, tmp_path / "repo")

    fields = {field.name: field for field in capabilities.interfaces[0].request.fields}
    assert fields["q"].location == "query"
    assert fields["q"].required is True
    assert fields["name"].location == "query"
    assert fields["name"].required is True


def test_fastapi_query_required_detection_handles_keywords_and_description_text(tmp_path: Path) -> None:
    source = """from fastapi import FastAPI, Query
from pydantic.fields import Required

app = FastAPI()

@app.get(\"/search\")
def search(
    omitted_default: str = Query(description=\"Search\"),
    alias_required: str = Query(alias=\"q\", default=Required),
    described_required: str = Query(description=\"x\", default=Required),
    optional_with_required_word: str = Query(None, description=\"Required by docs only\"),
):
    return {\"items\": []}
"""
    scan = _write_scan(tmp_path / "repo", {"main.py": ("Python", source)})

    capabilities = build_callable_capabilities(scan, tmp_path / "repo")

    fields = {field.name: field for field in capabilities.interfaces[0].request.fields}
    assert fields["omitted_default"].required is True
    assert fields["alias_required"].required is True
    assert fields["described_required"].required is True
    assert fields["optional_with_required_word"].required is False


def test_fastapi_explicit_parameter_helpers_control_location_and_required(tmp_path: Path) -> None:
    source = """from typing import Annotated
from fastapi import Body, FastAPI, Query
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str

@app.post(\"/items\")
def create_item(
    search: Item = Query(...),
    payload: str = Body(...),
    optional_query: Annotated[str, Query(None)] = "",
    required_query: Annotated[str, Query(...)] = "",
):
    return {\"ok\": True}
"""
    scan = _write_scan(tmp_path / "repo", {"main.py": ("Python", source)})

    capabilities = build_callable_capabilities(scan, tmp_path / "repo")

    fields = {field.name: field for field in capabilities.interfaces[0].request.fields}
    assert fields["search"].location == "query"
    assert fields["search"].required is True
    assert fields["payload"].location == "body"
    assert fields["payload"].required is True
    assert fields["optional_query"].location == "query"
    assert fields["optional_query"].required is False
    assert fields["required_query"].location == "query"
    assert fields["required_query"].required is True


# --------------------------------------------------------------------------- #
# Python — Flask (best-effort key inference)
# --------------------------------------------------------------------------- #

FLASK = """from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    name = data["name"]
    amount = data.get("amount")
    return jsonify({"ok": True})
"""


def test_detects_flask_route_infers_payload_keys(tmp_path: Path) -> None:
    root = tmp_path / "flask"
    scan = _write_scan(root, {"server.py": ("Python", FLASK)})

    result = build_callable_capabilities(scan, root)

    flask = [i for i in result.interfaces if i.framework == "flask"]
    assert len(flask) == 1
    interface = flask[0]
    assert interface.http_method == "POST"
    assert interface.route == "/submit"
    request_names = {f.name for f in interface.request.fields}
    assert request_names == {"name", "amount"}


# --------------------------------------------------------------------------- #
# Multi-stack aggregation + empty case
# --------------------------------------------------------------------------- #


def test_multi_stack_repo_detects_all_three(tmp_path: Path) -> None:
    root = tmp_path / "multi"
    scan = _write_scan(
        root,
        {
            "dotnet/CalculateWorkLoad.ashx": ("ASP.NET", ASHX),
            "dotnet/Models.cs": ("C#", CS_MODELS),
            "java/WorkController.java": ("Java", SPRING),
            "java/WorkModels.java": ("Java", SPRING_MODELS),
            "py/main.py": ("Python", FASTAPI),
        },
    )

    result = build_callable_capabilities(scan, root)

    stacks = {i.stack for i in result.interfaces}
    assert stacks == {"dotnet", "java", "python"}
    slugs = [i.slug for i in result.interfaces]
    assert len(slugs) == len(set(slugs))  # unique slugs


def test_repo_without_http_interfaces_returns_empty_with_note(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    scan = _write_scan(
        root,
        {"util.py": ("Python", "def add(a, b):\n    return a + b\n")},
    )

    result = build_callable_capabilities(scan, root)

    assert result.interfaces == []
    assert result.notes
    assert "No callable HTTP interfaces" in result.notes[0]
