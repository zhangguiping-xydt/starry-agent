"""Detect callable HTTP interfaces across .NET, Java, and Python sources.

This is a best-effort static reverse-engineering pass. It re-reads the source
files the scanner already catalogued (metadata-only) and applies regex/signature
heuristics — no real parser and no language runtime — to recognise HTTP entry
points and shallow-resolve their request/response payload contracts. When a
contract cannot be resolved it degrades to an unresolved placeholder with a TODO
note rather than inventing fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from repo_to_skill.models import (
    CallableCapabilitySet,
    CallableInterface,
    IoContract,
    IoField,
    ScanResult,
)

MAX_READ_SIZE = 1024 * 1024
SOURCE_LANGUAGES = {"Python", "Java", "C#", "ASP.NET"}

_FRAMEWORK_CALL_OWNERS = {
    "JsonConvert",
    "JavaScriptSerializer",
    "JObject",
    "JArray",
    "Convert",
    "HttpContext",
    "context",
    "Context",
    "Request",
    "Response",
    "Console",
    "Encoding",
    "StreamReader",
    "StreamWriter",
    "Stream",
    "Math",
    "String",
    "DateTime",
    "Guid",
    "Task",
    "System",
    "IO",
    "Path",
    "File",
    "Directory",
    "Activator",
    "Type",
    "Regex",
    "Enumerable",
}


@dataclass
class _Source:
    path: str
    language: str
    text: str


@dataclass
class _TypeDef:
    name: str
    language: str
    source_path: str
    fields: list[IoField] = field(default_factory=list)
    methods: dict[str, str] = field(default_factory=dict)  # method name -> return type


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #


def _safe_read(root: Path, rel_path: str) -> str:
    root_resolved = root.resolve()
    try:
        resolved = (root_resolved / rel_path).resolve()
    except OSError:
        return ""
    if resolved != root_resolved and root_resolved not in resolved.parents:
        return ""
    try:
        if not resolved.is_file() or resolved.stat().st_size > MAX_READ_SIZE:
            return ""
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _line_number(text: str, index: int) -> int:
    if index < 0:
        return 0
    return text.count("\n", 0, index) + 1


def _slugify(text: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", spaced).strip("-").lower()
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned or "interface"


def _env_name(slug: str, suffix: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()
    return f"{base}_{suffix}" if base else suffix


def _field_cli(name: str) -> str:
    return _slugify(name)


def _field_arg(name: str) -> str:
    return _slugify(name).replace("-", "_")


_JSON_TYPE_MAP = {
    "string": "string",
    "str": "string",
    "char": "string",
    "guid": "string",
    "uuid": "string",
    "datetime": "string",
    "datetimeoffset": "string",
    "date": "string",
    "time": "string",
    "instant": "string",
    "localdate": "string",
    "localdatetime": "string",
    "localtime": "string",
    "zoneddatetime": "string",
    "offsetdatetime": "string",
    "timestamp": "string",
    "int": "integer",
    "int16": "integer",
    "int32": "integer",
    "int64": "integer",
    "integer": "integer",
    "long": "integer",
    "short": "integer",
    "byte": "integer",
    "biginteger": "integer",
    "double": "number",
    "float": "number",
    "decimal": "number",
    "single": "number",
    "number": "number",
    "bigdecimal": "number",
    "bool": "boolean",
    "boolean": "boolean",
}

_ARRAY_PREFIXES = ("list", "array", "ienumerable", "collection", "ilist", "set", "sequence", "tuple")


def json_type_for(raw_type: str) -> str:
    """Map a source-language type name onto a JSON-schema scalar/array/object kind."""
    if not raw_type:
        return "unknown"
    cleaned = raw_type.strip().rstrip("?")
    if cleaned.endswith("[]"):
        return "array"
    base = re.split(r"[<\[]", cleaned, maxsplit=1)[0].strip()
    base = base.split(".")[-1]
    lowered = base.lower()
    if lowered in _JSON_TYPE_MAP:
        return _JSON_TYPE_MAP[lowered]
    if lowered.startswith(_ARRAY_PREFIXES):
        return "array"
    if lowered in {"dict", "dictionary", "map", "hashmap", "object"}:
        return "object"
    return "unknown"


def _balanced_body(text: str, brace_index: int) -> tuple[str, int]:
    depth = 0
    for position in range(brace_index, len(text)):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index + 1 : position], position
    return text[brace_index + 1 :], len(text)


def _first_brace_after(text: str, start: int) -> int:
    index = text.find("{", start)
    return index


# --------------------------------------------------------------------------- #
# Field parsers
# --------------------------------------------------------------------------- #

_TYPE_NON_NAMES = {
    "class",
    "struct",
    "interface",
    "enum",
    "void",
    "return",
    "static",
    "public",
    "private",
    "protected",
    "new",
    "this",
    "base",
    "if",
    "for",
    "while",
    "switch",
    "using",
    "namespace",
    "get",
    "set",
}

_CSHARP_FIELD_RE = re.compile(
    r"public\s+(?:virtual\s+|override\s+|readonly\s+|sealed\s+)*"
    r"([A-Za-z_][\w<>\[\],.?]*)\s+([A-Za-z_]\w*)\s*(\{\s*get|;|=[^=])"
)

_JAVA_FIELD_RE = re.compile(
    r"(?:private|public|protected)\s+(?:final\s+)?(?:static\s+)?"
    r"([A-Za-z_][\w<>\[\],.?]*)\s+([A-Za-z_]\w*)\s*(;|=[^=])"
)

_PY_FIELD_RE = re.compile(
    r"^[ \t]+([a-zA-Z_]\w*)\s*:\s*([A-Za-z_][\w\[\], .\"'|]*?)\s*(=\s*.+)?$",
    re.MULTILINE,
)


def _is_optional_annotation(annotation: str) -> bool:
    lowered = annotation.lower()
    return "optional" in lowered or annotation.strip().endswith("| none") or "none" in lowered.split("|")


def _parse_csharp_fields(body: str, source_path: str) -> list[IoField]:
    fields: list[IoField] = []
    seen: set[str] = set()
    for match in _CSHARP_FIELD_RE.finditer(body):
        raw_type, name = match.group(1), match.group(2)
        if raw_type in _TYPE_NON_NAMES or name in _TYPE_NON_NAMES or name in seen:
            continue
        seen.add(name)
        fields.append(
            IoField(
                name=name,
                type=raw_type,
                required="?" not in raw_type,
                source_path=source_path,
                confidence=0.6,
            )
        )
    return fields


def _parse_java_fields(body: str, source_path: str) -> list[IoField]:
    fields: list[IoField] = []
    seen: set[str] = set()
    for match in _JAVA_FIELD_RE.finditer(body):
        raw_type, name = match.group(1), match.group(2)
        if raw_type in _TYPE_NON_NAMES or name in _TYPE_NON_NAMES or name in seen:
            continue
        seen.add(name)
        fields.append(
            IoField(
                name=name,
                type=raw_type,
                required=json_type_for(raw_type) in {"integer", "number", "boolean"},
                source_path=source_path,
                confidence=0.6,
            )
        )
    return fields


def _parse_java_record_params(param_text: str, source_path: str) -> list[IoField]:
    fields: list[IoField] = []
    for part in param_text.split(","):
        tokens = part.strip().split()
        if len(tokens) < 2:
            continue
        raw_type, name = tokens[-2], tokens[-1]
        fields.append(
            IoField(
                name=name,
                type=raw_type,
                required=True,
                source_path=source_path,
                confidence=0.6,
            )
        )
    return fields


def _parse_python_fields(body: str, source_path: str) -> list[IoField]:
    fields: list[IoField] = []
    seen: set[str] = set()
    for line in body.splitlines():
        if "def " in line or "=" in line.split(":", 1)[0]:
            continue
        match = _PY_FIELD_RE.match(line)
        if not match:
            continue
        name, annotation, default = match.group(1), match.group(2).strip(), match.group(3)
        if name.startswith("_") or name in {"model_config", "Config"} or name in seen:
            continue
        seen.add(name)
        fields.append(
            IoField(
                name=name,
                type=annotation,
                required=default is None and not _is_optional_annotation(annotation),
                source_path=source_path,
                confidence=0.6,
            )
        )
    return fields


# --------------------------------------------------------------------------- #
# Type index
# --------------------------------------------------------------------------- #

_CSHARP_METHOD_RE = re.compile(
    r"public\s+(?:static\s+|virtual\s+|override\s+|async\s+)*"
    r"([A-Za-z_][\w<>\[\],.?]*)\s+([A-Za-z_]\w*)\s*\("
)
_JAVA_METHOD_RE = re.compile(
    r"(?:public|protected)\s+(?:static\s+|final\s+)*"
    r"([A-Za-z_][\w<>\[\],.?]*)\s+([A-Za-z_]\w*)\s*\("
)


def _index_methods(body: str, pattern: re.Pattern[str]) -> dict[str, str]:
    methods: dict[str, str] = {}
    for match in pattern.finditer(body):
        return_type, name = match.group(1), match.group(2)
        if return_type in _TYPE_NON_NAMES or name in _TYPE_NON_NAMES:
            continue
        methods.setdefault(name, return_type)
    return methods


def _index_brace_types(source: _Source, parse_fields, method_pattern) -> list[_TypeDef]:
    defs: list[_TypeDef] = []
    text = source.text
    for match in re.finditer(r"\b(?:class|struct|record)\s+([A-Za-z_]\w*)", text):
        name = match.group(1)
        record_params = re.match(r"\s*\(([^)]*)\)", text[match.end():])
        brace = _first_brace_after(text, match.end())
        body = ""
        if brace != -1:
            body, _ = _balanced_body(text, brace)
        fields = parse_fields(body, source.path) if body else []
        if record_params:
            fields = _parse_java_record_params(record_params.group(1), source.path) + fields
        methods = _index_methods(body, method_pattern) if body else {}
        defs.append(
            _TypeDef(
                name=name,
                language=source.language,
                source_path=source.path,
                fields=fields,
                methods=methods,
            )
        )
    return defs


def _index_python_types(source: _Source) -> list[_TypeDef]:
    defs: list[_TypeDef] = []
    text = source.text
    for match in re.finditer(r"^class\s+([A-Za-z_]\w*)\s*(\([^)]*\))?\s*:", text, re.MULTILINE):
        name = match.group(1)
        body = _python_class_block(text, match.end())
        defs.append(
            _TypeDef(
                name=name,
                language=source.language,
                source_path=source.path,
                fields=_parse_python_fields(body, source.path),
            )
        )
    return defs


def _python_class_block(text: str, start: int) -> str:
    lines = text[start:].splitlines()
    collected: list[str] = []
    base_indent: int | None = None
    started = False
    for line in lines:
        if not line.strip():
            collected.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if not started:
            base_indent = indent
            started = True
        if indent < (base_indent or 0):
            break
        collected.append(line)
    return "\n".join(collected)


def _index_types(sources: list[_Source]) -> dict[str, list[_TypeDef]]:
    index: dict[str, list[_TypeDef]] = {}
    for source in sources:
        if source.language in {"C#", "ASP.NET"}:
            defs = _index_brace_types(source, _parse_csharp_fields, _CSHARP_METHOD_RE)
        elif source.language == "Java":
            defs = _index_brace_types(source, _parse_java_fields, _JAVA_METHOD_RE)
        elif source.language == "Python":
            defs = _index_python_types(source)
        else:
            defs = []
        for definition in defs:
            index.setdefault(definition.name, []).append(definition)
    return index


def _resolve_contract(type_name: str, index: dict[str, list[_TypeDef]]) -> IoContract:
    candidates = index.get(type_name) or []
    chosen = next((definition for definition in candidates if definition.fields), None) or (
        candidates[0] if candidates else None
    )
    if chosen is None:
        return IoContract(
            model_name=type_name or "unknown",
            unresolved=True,
            confidence=0.2,
            notes=[f"TODO: could not resolve payload type '{type_name}' in scanned sources."],
        )
    if not chosen.fields:
        return IoContract(
            model_name=type_name,
            unresolved=True,
            confidence=0.3,
            notes=[f"TODO: type '{type_name}' resolved at {chosen.source_path} but no public fields were parsed."],
            fields=[],
        )
    for io_field in chosen.fields:
        io_field.source_symbol = type_name
    return IoContract(
        model_name=type_name,
        fields=chosen.fields,
        unresolved=False,
        confidence=0.7,
    )


def _resolve_method_return_type(method_name: str, index: dict[str, list[_TypeDef]]) -> str:
    for definitions in index.values():
        for definition in definitions:
            if method_name in definition.methods:
                return definition.methods[method_name]
    return ""


def _unwrap_response_type(raw: str) -> str:
    cleaned = raw.strip()
    for wrapper in ("ResponseEntity", "ActionResult", "Task", "Mono", "Flux", "Optional", "List", "IEnumerable"):
        inner = re.match(rf"{wrapper}<(.+)>$", cleaned)
        if inner:
            cleaned = inner.group(1).strip()
    return cleaned


def _unresolved_contract(reason: str) -> IoContract:
    return IoContract(model_name="unknown", unresolved=True, confidence=0.2, notes=[f"TODO: {reason}"])


# --------------------------------------------------------------------------- #
# .NET detection
# --------------------------------------------------------------------------- #

_DESERIALIZE_RE = re.compile(r"Deserialize(?:Object)?<([A-Za-z_][\w.]*)>")
_DESERIALIZE_TYPEOF_RE = re.compile(r"Deserialize\([^,]+,\s*typeof\(([A-Za-z_][\w.]*)\)")
_SERIALIZE_VAR_RE = re.compile(r"Serialize(?:Object)?\(\s*([A-Za-z_]\w*)")


def _find_ashx_path(sources: list[_Source], class_name: str) -> str:
    for source in sources:
        if source.language == "ASP.NET" and source.path.lower().endswith((".ashx", ".asmx")):
            if re.search(rf'Class="[^"]*\b{re.escape(class_name)}\b', source.text):
                return source.path
    return ""


def _local_object_types(body: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    pattern = r"\b([A-Z][A-Za-z0-9_]*)\s+([a-zA-Z_]\w*)\s*=\s*new\s+\1\s*\("
    for match in re.finditer(pattern, body):
        variables[match.group(2)] = match.group(1)
    return variables


def _business_method_call(body: str) -> tuple[str, str]:
    local_types = _local_object_types(body)
    for match in re.finditer(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(", body):
        owner, method = match.group(1), match.group(2)
        resolved_owner = local_types.get(owner, owner)
        if resolved_owner in _FRAMEWORK_CALL_OWNERS:
            continue
        if not resolved_owner[:1].isupper():
            continue
        return resolved_owner, method
    return "", ""


def _detect_dotnet_handlers(
    sources: list[_Source], index: dict[str, list[_TypeDef]]
) -> list[CallableInterface]:
    interfaces: list[CallableInterface] = []
    for source in sources:
        if source.language not in {"C#", "ASP.NET"}:
            continue
        text = source.text
        if "IHttpHandler" not in text or "ProcessRequest" not in text:
            continue
        class_match = re.search(r"class\s+([A-Za-z_]\w*)\b[^{]*IHttpHandler", text)
        if not class_match:
            continue
        class_name = class_match.group(1)
        method_match = re.search(r"ProcessRequest\s*\([^)]*\)", text)
        body = ""
        if method_match:
            brace = _first_brace_after(text, method_match.end())
            if brace != -1:
                body, _ = _balanced_body(text, brace)
        request_type = ""
        for pattern in (_DESERIALIZE_RE, _DESERIALIZE_TYPEOF_RE):
            found = pattern.search(body)
            if found:
                request_type = found.group(1).split(".")[-1]
                break
        reads_body = bool(
            request_type
            or re.search(r"InputStream|Request\.Form|ReadToEnd|BinaryRead|Request\.Files", body)
        )
        http_method = "POST" if reads_body else "GET"
        request_contract = (
            _resolve_contract(request_type, index)
            if request_type
            else _unresolved_contract("no request payload type found in ProcessRequest body")
        )
        response_type = ""
        business = ""
        serialize_var = _SERIALIZE_VAR_RE.search(body)
        if serialize_var:
            var = serialize_var.group(1)
            decl = re.search(rf"\b([A-Za-z_][\w.]*)\s+{re.escape(var)}\s*=\s*([^;]+);", body)
            if decl:
                decl_type, decl_rhs = decl.group(1), decl.group(2)
                if decl_type not in {"var", "string", "object"}:
                    response_type = decl_type.split(".")[-1]
                rhs_call = _business_method_call(decl_rhs)
                if rhs_call[0]:
                    business = f"{rhs_call[0]}.{rhs_call[1]}"
        if not business:
            owner, method = _business_method_call(body)
            business = f"{owner}.{method}" if owner else ""
        business_method = business
        if not response_type and "." in business:
            method_name = business.split(".", 1)[1]
            response_type = _unwrap_response_type(_resolve_method_return_type(method_name, index)).split(".")[-1]
        response_contract = (
            _resolve_contract(response_type, index)
            if response_type
            else _unresolved_contract("could not resolve response payload type from handler body")
        )
        handler_path = _find_ashx_path(sources, class_name) or source.path
        slug = _slugify(class_name)
        interfaces.append(
            CallableInterface(
                id=f"dotnet:{handler_path}:{http_method}",
                slug=slug,
                stack="dotnet",
                framework="asp.net-ihttphandler",
                http_method=http_method,
                route=handler_path,
                handler_symbol=class_name,
                handler_path=handler_path,
                handler_line=_line_number(text, class_match.start()),
                business_method=business_method,
                request=request_contract,
                response=response_contract,
                endpoint_env=_env_name(slug, "ENDPOINT"),
                token_env=_env_name(slug, "TOKEN"),
                side_effects="read" if http_method == "GET" else "unknown",
                confidence=0.65 if not request_contract.unresolved else 0.4,
                evidence=[f"{source.path}: IHttpHandler.ProcessRequest"],
            )
        )
    return interfaces


_HTTP_ATTR_RE = re.compile(r"\[Http(Get|Post|Put|Delete|Patch)(?:\(\s*\"([^\"]*)\"\s*\))?\]")
_FROMBODY_RE = re.compile(r"\[FromBody\]\s*([A-Za-z_][\w<>.]*)\s+\w+")


def _detect_dotnet_controllers(
    sources: list[_Source], index: dict[str, list[_TypeDef]]
) -> list[CallableInterface]:
    interfaces: list[CallableInterface] = []
    for source in sources:
        if source.language != "C#":
            continue
        text = source.text
        if "[ApiController]" not in text and "ControllerBase" not in text and "Controller" not in text:
            continue
        if "[Http" not in text:
            continue
        class_match = re.search(r"class\s+([A-Za-z_]\w*Controller)\b", text)
        if not class_match:
            continue
        class_name = class_match.group(1)
        base_route_match = re.search(r"\[Route\(\s*\"([^\"]*)\"\s*\)\]", text[: class_match.start()] + text[class_match.start():class_match.end()+200])
        base_route = base_route_match.group(1) if base_route_match else ""
        base_route = base_route.replace("[controller]", class_name.removesuffix("Controller"))
        for attr in _HTTP_ATTR_RE.finditer(text):
            http_method = attr.group(1).upper()
            method_route = attr.group(2) or ""
            tail = text[attr.end(): attr.end() + 400]
            sig = re.search(r"public\s+(?:async\s+)?([A-Za-z_][\w<>.,\[\] ]*?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", tail)
            if not sig:
                continue
            action_name = sig.group(2)
            params = sig.group(3)
            body_match = _FROMBODY_RE.search(params)
            request_type = body_match.group(1).split(".")[-1] if body_match else ""
            response_type = _unwrap_response_type(sig.group(1)).split(".")[-1]
            route = "/".join(part.strip("/") for part in (base_route, method_route) if part.strip("/"))
            route = route or action_name
            slug = _slugify(f"{class_name.removesuffix('Controller')}-{action_name}")
            request_contract = (
                _resolve_contract(request_type, index)
                if request_type
                else _unresolved_contract("controller action has no [FromBody] payload type")
            )
            response_contract = (
                _resolve_contract(response_type, index)
                if response_type and json_type_for(response_type) == "unknown"
                else _unresolved_contract("response type is a framework or scalar result")
            )
            interfaces.append(
                CallableInterface(
                    id=f"dotnet:{source.path}:{action_name}:{http_method}",
                    slug=slug,
                    stack="dotnet",
                    framework="asp.net-webapi",
                    http_method=http_method,
                    route=route,
                    handler_symbol=f"{class_name}.{action_name}",
                    handler_path=source.path,
                    handler_line=_line_number(text, attr.start()),
                    request=request_contract,
                    response=response_contract,
                    endpoint_env=_env_name(slug, "ENDPOINT"),
                    token_env=_env_name(slug, "TOKEN"),
                    side_effects="read" if http_method == "GET" else "unknown",
                    confidence=0.6 if not request_contract.unresolved else 0.4,
                    evidence=[f"{source.path}: {class_name}.{action_name} [{http_method}]"],
                )
            )
    return interfaces


# --------------------------------------------------------------------------- #
# Java detection
# --------------------------------------------------------------------------- #

_SPRING_MAPPING_RE = re.compile(
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping(?:\(\s*([^)]*)\))?"
)
_REQUEST_BODY_RE = re.compile(
    r"@RequestBody\s*(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s*)*(?:final\s+)?([A-Za-z_][\w<>.]*)\s+\w+"
)
_JAVA_SIG_PREFIX_RE = re.compile(
    r"public\s+(?:final\s+)?([A-Za-z_][\w<>.,\[\] ]*?)\s+([A-Za-z_]\w*)\s*\("
)


def _balanced_paren_text(text: str, open_index: int) -> str:
    depth = 0
    for position in range(open_index, len(text)):
        char = text[position]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : position]
    return text[open_index + 1 :]


def _java_signature(tail: str) -> tuple[str, str, str] | None:
    match = _JAVA_SIG_PREFIX_RE.search(tail)
    if not match:
        return None
    return_type, action_name = match.group(1), match.group(2)
    params = _balanced_paren_text(tail, match.end() - 1)
    return return_type, action_name, params


def _mapping_route(attr_args: str) -> str:
    if not attr_args:
        return ""
    match = re.search(r'"([^"]*)"', attr_args)
    return match.group(1) if match else ""


def _spring_request_method(annotation: str, attr_args: str) -> str:
    if annotation != "Request":
        return annotation.upper()
    method = re.search(r"method\s*=\s*RequestMethod\.(\w+)", attr_args)
    return method.group(1).upper() if method else "POST"


def _detect_spring(source: _Source, index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    text = source.text
    if "@RestController" not in text and "@Controller" not in text:
        return []
    interfaces: list[CallableInterface] = []
    class_match = re.search(r"class\s+([A-Za-z_]\w*)", text)
    class_name = class_match.group(1) if class_match else Path(source.path).stem
    base_route = ""
    class_anchor = class_match.start() if class_match else len(text)
    base_mapping = re.search(r"@RequestMapping\(\s*([^)]*)\)", text[:class_anchor])
    if base_mapping:
        base_route = _mapping_route(base_mapping.group(1))
    for mapping in _SPRING_MAPPING_RE.finditer(text):
        # Skip the class-level @RequestMapping (it sits before the class body and
        # is captured separately as base_mapping); only method mappings yield routes.
        if base_mapping and class_match and mapping.start() < base_mapping.end():
            continue
        annotation, attr_args = mapping.group(1), mapping.group(2) or ""
        http_method = _spring_request_method(annotation, attr_args)
        method_route = _mapping_route(attr_args)
        tail = text[mapping.end(): mapping.end() + 600]
        sig = _java_signature(tail)
        if sig is None:
            continue
        return_type, action_name, params = sig
        body_match = _REQUEST_BODY_RE.search(params)
        request_type = body_match.group(1).split("<")[0].split(".")[-1] if body_match else ""
        response_type = _unwrap_response_type(return_type).split(".")[-1]
        route = "/".join(part.strip("/") for part in (base_route, method_route) if part.strip("/"))
        route = "/" + route if route else "/" + action_name
        slug = _slugify(f"{class_name}-{action_name}")
        request_contract = (
            _resolve_contract(request_type, index)
            if request_type
            else _unresolved_contract("no @RequestBody payload type on handler method")
        )
        response_contract = (
            _resolve_contract(response_type, index)
            if response_type and json_type_for(response_type) == "unknown"
            else _unresolved_contract("response type is a framework or scalar result")
        )
        interfaces.append(
            CallableInterface(
                id=f"java:{source.path}:{action_name}:{http_method}",
                slug=slug,
                stack="java",
                framework="spring",
                http_method=http_method,
                route=route,
                handler_symbol=f"{class_name}.{action_name}",
                handler_path=source.path,
                handler_line=_line_number(text, mapping.start()),
                request=request_contract,
                response=response_contract,
                endpoint_env=_env_name(slug, "ENDPOINT"),
                token_env=_env_name(slug, "TOKEN"),
                side_effects="read" if http_method == "GET" else "unknown",
                confidence=0.65 if not request_contract.unresolved else 0.4,
                evidence=[f"{source.path}: {class_name}.{action_name} ({annotation}Mapping)"],
            )
        )
    return interfaces


_JAXRS_METHOD_RE = re.compile(r"@(GET|POST|PUT|DELETE|PATCH)\b")


def _detect_jaxrs(source: _Source, index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    text = source.text
    if "@Path" not in text or not _JAXRS_METHOD_RE.search(text):
        return []
    interfaces: list[CallableInterface] = []
    class_match = re.search(r"class\s+([A-Za-z_]\w*)", text)
    class_name = class_match.group(1) if class_match else Path(source.path).stem
    class_anchor = class_match.start() if class_match else len(text)
    base_path_match = re.search(r'@Path\(\s*"([^"]*)"\s*\)', text[:class_anchor])
    base_route = base_path_match.group(1) if base_path_match else ""
    for verb in _JAXRS_METHOD_RE.finditer(text):
        http_method = verb.group(1)
        tail = text[verb.end(): verb.end() + 600]
        method_path_match = re.search(r'@Path\(\s*"([^"]*)"\s*\)', tail[:200])
        method_route = method_path_match.group(1) if method_path_match else ""
        sig = _java_signature(tail)
        if sig is None:
            continue
        return_type, action_name, params = sig
        entity_type = ""
        for part in params.split(","):
            tokens = part.strip().split()
            if len(tokens) == 2 and not tokens[0].startswith("@"):
                entity_type = tokens[0].split("<")[0].split(".")[-1]
                break
        response_type = _unwrap_response_type(return_type).split(".")[-1]
        route = "/".join(part.strip("/") for part in (base_route, method_route) if part.strip("/"))
        route = "/" + route if route else "/" + action_name
        slug = _slugify(f"{class_name}-{action_name}")
        request_contract = (
            _resolve_contract(entity_type, index)
            if entity_type
            else _unresolved_contract("no request entity parameter on JAX-RS method")
        )
        response_contract = (
            _resolve_contract(response_type, index)
            if response_type and json_type_for(response_type) == "unknown"
            else _unresolved_contract("response type is a framework or scalar result")
        )
        interfaces.append(
            CallableInterface(
                id=f"java:{source.path}:{action_name}:{http_method}",
                slug=slug,
                stack="java",
                framework="jax-rs",
                http_method=http_method,
                route=route,
                handler_symbol=f"{class_name}.{action_name}",
                handler_path=source.path,
                handler_line=_line_number(text, verb.start()),
                request=request_contract,
                response=response_contract,
                endpoint_env=_env_name(slug, "ENDPOINT"),
                token_env=_env_name(slug, "TOKEN"),
                side_effects="read" if http_method == "GET" else "unknown",
                confidence=0.6 if not request_contract.unresolved else 0.4,
                evidence=[f"{source.path}: {class_name}.{action_name} (@{http_method})"],
            )
        )
    return interfaces


def _detect_java(sources: list[_Source], index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    interfaces: list[CallableInterface] = []
    for source in sources:
        if source.language != "Java":
            continue
        interfaces.extend(_detect_spring(source, index))
        interfaces.extend(_detect_jaxrs(source, index))
    return interfaces


# --------------------------------------------------------------------------- #
# Python detection
# --------------------------------------------------------------------------- #

_FASTAPI_ROUTE_RE = re.compile(
    r"@(\w+)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']([^)]*)\)"
)
_FLASK_ROUTE_RE = re.compile(
    r"@(\w+)\.route\(\s*[\"']([^\"']+)[\"']([^)]*)\)"
)
_PY_DEF_RE = re.compile(r"(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")


def _find_annotation_colon(text: str) -> int:
    """Return the index of the first top-level ``:`` in ``text``.

    Brackets and string literals are skipped so annotations like
    ``dict[str, int]`` or ``Literal[\"a:b\"]`` do not terminate early.
    """
    depth = 0
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            continue
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            if depth > 0:
                depth -= 1
            continue
        if char == ":" and depth == 0:
            return index
    return -1


def _find_py_def(text: str, start: int) -> tuple[int, int, str, str, str] | None:
    """Locate the next ``def name(...)[: -> ann]: ...`` signature starting at ``start``.

    Scans parameter and return-annotation parentheses with depth tracking so
    signatures like ``def f(payload: Annotated[Item, Body()]):`` and
    ``def f(q: str = Query(\"x\")) -> Response[Item]:`` parse correctly. A regex
    using ``([^)]*)`` would terminate at the first inner ``)`` and drop the
    whole handler.

    Returns ``(match_start, signature_end, name, params, return_annotation)``
    where ``signature_end`` is the index just past the terminating ``:``,
    or ``None`` if no signature is found.
    """
    opener = _PY_DEF_RE.search(text, start)
    if opener is None:
        return None
    name = opener.group(1)
    paren_start = opener.end() - 1  # position of '('
    depth = 0
    param_end = -1
    for index in range(paren_start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                param_end = index
                break
    if param_end == -1:
        return None
    params = text[paren_start + 1:param_end]
    tail = text[param_end + 1:]
    return_annotation = ""
    stripped = tail.lstrip()
    if stripped.startswith("->"):
        rest = stripped[2:].lstrip()
        colon = _find_annotation_colon(rest)
        if colon == -1:
            return None
        return_annotation = rest[:colon].strip()
        body_colon_offset = len(tail) - len(rest) + colon
    else:
        body_match = re.match(r"\s*:", tail)
        if body_match is None:
            return None
        body_colon_offset = body_match.end() - 1
    signature_end = param_end + 1 + body_colon_offset + 1
    return (opener.start(), signature_end, name, params, return_annotation)


def _fastapi_path_param_names(route: str) -> list[str]:
    """Return the path parameter names declared in a FastAPI route, in order.

    Accepts ``{name}`` and ``{name: converter}`` forms. Path params also include
    Starlette's angle-bracket form ``<name>`` for safety, but FastAPI's canonical
    form is ``{name}``.
    """
    names: list[str] = []
    for match in re.finditer(r"\{([A-Za-z_]\w*)(?::[^}]*)?\}", route):
        names.append(match.group(1))
    return names


def _fastapi_split_params(params: str) -> list[tuple[str, str, str]]:
    """Split a Python parameter list into (name, annotation, default) tuples.

    Annotations and defaults are stripped of leading/trailing whitespace. Parameters
    without an annotation yield an empty annotation string; parameters without a
    default yield an empty default string.
    """
    parts: list[tuple[str, str, str]] = []
    depth = 0
    current = ""
    for char in params:
        if char == "," and depth == 0:
            parts.append(_fastapi_parse_param(current))
            current = ""
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        current += char
    if current.strip():
        parts.append(_fastapi_parse_param(current))
    return parts


def _fastapi_parse_param(text: str) -> tuple[str, str, str]:
    cleaned = text.strip()
    if not cleaned or cleaned.startswith("*"):
        return ("", "", "")
    # Strip any leading decorators/annotations like @Body(...). Keep this simple:
    # the part before the first ":" is the name (possibly with leading decorators
    # which we ignore because they contain no ":" at the top level).
    if ":" in cleaned:
        name_part, rest = cleaned.split(":", 1)
        name = name_part.strip().split("=")[-1].strip()
        annotation_and_default = rest.strip()
    else:
        # No annotation — "name" or "name=default"
        name, default = (cleaned.split("=", 1) + [""])[:2]
        return (name.strip(), "", default.strip())
    if "=" in annotation_and_default:
        annotation, default = annotation_and_default.split("=", 1)
        annotation = annotation.strip()
        default = default.strip()
    else:
        annotation = annotation_and_default.strip()
        default = ""
    # Name may still carry leading decorator remnants like "Body(...) payload" —
    # take the last whitespace-separated identifier as the name.
    name = name.split()[-1] if name else ""
    return (name, annotation, default)


def _fastapi_base_type(annotation: str) -> str:
    """Return the base type name for a FastAPI handler parameter annotation.

    Handles three common forms:
    - ``int`` / ``str`` / ``Item``                    → returned verbatim (module-stripped)
    - ``Optional[Item]`` / ``list[Item]``             → outer wrapper preserved
    - ``Annotated[Item, Body()]`` / ``Annotated[Item, Body(), ...]``
                                                      → ``Item`` (first type argument)
    - ``dict`` / ``dict[str, int]``                   → preserved so dict body detection works
    """
    cleaned = annotation.strip()
    if not cleaned:
        return ""
    # Default-value tail is already stripped by the caller, but be defensive:
    cleaned = re.split(r"\s*=\s*", cleaned, maxsplit=1)[0].strip()
    annotated = re.match(r"(?:typing\.)?Annotated\s*\[\s*([^\],]+)", cleaned, re.IGNORECASE)
    if annotated:
        return annotated.group(1).strip().split(".")[-1]
    return re.split(r"\s*\[\s*", cleaned, maxsplit=1)[0].strip().split(".")[-1]


_FASTAPI_CONTEXT_PARAM_NAMES = {"self", "cls"}
_FASTAPI_CONTEXT_TYPES = {
    "Request",
    "WebSocket",
    "Response",
    "BackgroundTasks",
    "HTTPConnection",
    "State",
}
_FASTAPI_PARAM_HELPERS = {"Query", "Path", "Body", "Cookie", "Header", "Form", "File"}


def _fastapi_is_context_param(name: str, annotation_base: str) -> bool:
    return name in _FASTAPI_CONTEXT_PARAM_NAMES or annotation_base in _FASTAPI_CONTEXT_TYPES


def _fastapi_helper_calls(*texts: str) -> list[tuple[str, str]]:
    """Return FastAPI parameter helper calls found in defaults/Annotated metadata."""
    calls: list[tuple[str, str]] = []
    for text in texts:
        for match in re.finditer(r"(?:fastapi\.)?(Query|Path|Body)\s*\(", text or ""):
            calls.append((match.group(1), _balanced_paren_text(text, match.end() - 1)))
    return calls


def _fastapi_split_helper_args(args: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    current = ""
    for char in args:
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            current += char
            continue
        if char == "," and depth == 0:
            if current.strip():
                parts.append(current.strip())
            current = ""
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth > 0:
                depth -= 1
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def _fastapi_default_value_required(value: str) -> bool:
    return value.strip() in {"...", "Ellipsis", "Required"}


def _fastapi_helper_required(args: str) -> bool | None:
    positional: list[str] = []
    default_value: str | None = None
    for part in _fastapi_split_helper_args(args):
        keyword = re.fullmatch(r"([A-Za-z_]\w*)\s*=\s*(.+)", part, re.DOTALL)
        if keyword:
            if keyword.group(1) == "default":
                default_value = keyword.group(2).strip()
            continue
        positional.append(part)

    if default_value is not None:
        return _fastapi_default_value_required(default_value)
    if positional:
        return _fastapi_default_value_required(positional[0])
    return True


def _fastapi_param_location(name: str, annotation: str, default: str, path_param_names: set[str]) -> str | None:
    for helper_name, _args in _fastapi_helper_calls(annotation, default):
        if helper_name == "Query":
            return "query"
        if helper_name == "Body":
            return "body"
        if helper_name == "Path" and name in path_param_names:
            return "path"
    return None


def _fastapi_param_required(default: str, annotation: str = "") -> bool:
    """Return whether a FastAPI handler parameter should be considered required."""
    for _helper_name, args in _fastapi_helper_calls(annotation):
        helper_required = _fastapi_helper_required(args)
        if helper_required is not None:
            return helper_required
    for _helper_name, args in _fastapi_helper_calls(default):
        helper_required = _fastapi_helper_required(args)
        if helper_required is not None:
            return helper_required
    cleaned = default.strip()
    if not cleaned or cleaned == "...":
        return True
    return False


def _detect_fastapi(source: _Source, index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    text = source.text
    if "@" not in text or (".get(" not in text and ".post(" not in text and ".put(" not in text
                           and ".delete(" not in text and ".patch(" not in text):
        return []
    interfaces: list[CallableInterface] = []
    for route_match in _FASTAPI_ROUTE_RE.finditer(text):
        http_method = route_match.group(2).upper()
        route = route_match.group(3)
        decorator_args = route_match.group(4)
        def_info = _find_py_def(text, route_match.end())
        if def_info is None:
            continue
        _def_start, _def_end, action_name, params, return_annotation = def_info

        path_param_names = set(_fastapi_path_param_names(route))
        path_fields: list[IoField] = []
        query_fields: list[IoField] = []
        body_fields: list[IoField] = []
        body_type = ""
        body_is_dict = False
        for name, annotation, default in _fastapi_split_params(params):
            if not name:
                continue
            annotation_base = _fastapi_base_type(annotation)
            if _fastapi_is_context_param(name, annotation_base):
                continue
            explicit_location = _fastapi_param_location(name, annotation, default, path_param_names)
            location = explicit_location
            if location is None:
                if name in path_param_names:
                    location = "path"
                elif annotation_base in index or annotation_base.lower() in {"dict", "dictionary"} or annotation_base.lower().startswith("dict["):
                    location = "body"
                else:
                    location = "query"
            if location == "path":
                # Path parameter: FastAPI binds it from {name} in the route.
                path_fields.append(
                    IoField(
                        name=name,
                        type=annotation_base or "string",
                        required=True,
                        source_path=source.path,
                        source_symbol=action_name,
                        confidence=0.8,
                        location="path",
                    )
                )
                continue
            if location == "query":
                query_fields.append(
                    IoField(
                        name=name,
                        type=annotation_base or "string",
                        required=_fastapi_param_required(default, annotation),
                        source_path=source.path,
                        source_symbol=action_name,
                        confidence=0.7,
                        location="query",
                    )
                )
                continue
            if annotation_base in index:
                body_type = annotation_base
            elif annotation_base.lower() in {"dict", "dictionary"} or annotation_base.lower().startswith("dict["):
                body_is_dict = True
            else:
                body_fields.append(
                    IoField(
                        name=name,
                        type=annotation_base or "string",
                        required=_fastapi_param_required(default, annotation),
                        source_path=source.path,
                        source_symbol=action_name,
                        confidence=0.7,
                        location="body",
                    )
                )

        response_type = ""
        response_model = re.search(r"response_model\s*=\s*([A-Za-z_]\w*)", decorator_args)
        if response_model:
            response_type = response_model.group(1)
        elif return_annotation:
            response_type = _unwrap_response_type(return_annotation).split(".")[-1]
        slug = _slugify(f"{Path(source.path).stem}-{action_name}")

        body_contract = (
            _resolve_contract(body_type, index)
            if body_type
            else (
                IoContract(
                    model_name="dict",
                    unresolved=True,
                    confidence=0.3,
                    notes=["Handler accepts a raw dict body; pass a JSON object via --json-body."],
                )
                if body_is_dict
                else None
            )
        )
        if body_contract is None and body_fields:
            body_contract = IoContract(
                model_name=f"{action_name}_body",
                fields=[],
                unresolved=False,
                confidence=0.6,
                notes=[],
            )
        if body_contract is None:
            # GET handlers typically have no body; POST/PUT/PATCH without a body
            # param is still callable with an empty payload.
            body_contract = IoContract(
                model_name="none",
                unresolved=True,
                confidence=0.3,
                notes=["No typed request body parameter detected; pass --json-body '{}' if a body is required."],
            )

        # Merge path/query fields into the contract's field list so callers know
        # they must supply them. location distinguishes them from body fields.
        merged_fields = list(path_fields) + list(query_fields) + list(body_fields) + list(body_contract.fields)
        request_contract = IoContract(
            model_name=body_contract.model_name,
            media_type=body_contract.media_type,
            fields=merged_fields,
            confidence=body_contract.confidence,
            unresolved=body_contract.unresolved or body_is_dict,
            notes=list(body_contract.notes),
        )

        response_contract = (
            _resolve_contract(response_type, index)
            if response_type and response_type in index
            else _unresolved_contract("response model not resolvable to a scanned type")
        )
        interfaces.append(
            CallableInterface(
                id=f"python:{source.path}:{action_name}:{http_method}",
                slug=slug,
                stack="python",
                framework="fastapi",
                http_method=http_method,
                route=route,
                handler_symbol=action_name,
                handler_path=source.path,
                handler_line=_line_number(text, route_match.start()),
                request=request_contract,
                response=response_contract,
                endpoint_env=_env_name(slug, "ENDPOINT"),
                token_env=_env_name(slug, "TOKEN"),
                side_effects="read" if http_method == "GET" else "unknown",
                confidence=0.65 if not request_contract.unresolved else 0.4,
                evidence=[f"{source.path}: {action_name} (@{route_match.group(1)}.{http_method.lower()})"],
            )
        )
    return interfaces


def _flask_payload_fields(body: str, source_path: str) -> list[IoField]:
    keys: list[str] = []
    for match in re.finditer(r"(?:get_json\(\)|request\.json|payload|data|body)\s*(?:\.get\(\s*[\"'](\w+)[\"']|\[\s*[\"'](\w+)[\"'])", body):
        key = match.group(1) or match.group(2)
        if key and key not in keys:
            keys.append(key)
    return [
        IoField(name=key, type="unknown", required=False, source_path=source_path, confidence=0.3)
        for key in keys
    ]


def _detect_flask(source: _Source, index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    text = source.text
    if ".route(" not in text:
        return []
    interfaces: list[CallableInterface] = []
    for route_match in _FLASK_ROUTE_RE.finditer(text):
        route = route_match.group(2)
        decorator_args = route_match.group(3)
        methods_match = re.search(r"methods\s*=\s*\[([^\]]*)\]", decorator_args)
        methods = (
            [token.strip().strip("\"'").upper() for token in methods_match.group(1).split(",") if token.strip()]
            if methods_match
            else ["GET"]
        )
        def_match = _find_py_def(text, route_match.end())
        if def_match is None:
            continue
        _def_start, def_end, action_name = def_match[0], def_match[1], def_match[2]
        body = _python_class_block(text, def_end)
        for http_method in methods:
            if http_method == "HEAD" or http_method == "OPTIONS":
                continue
            fields = _flask_payload_fields(body, source.path) if http_method in {"POST", "PUT", "PATCH"} else []
            if fields:
                request_contract = IoContract(
                    model_name=f"{action_name}_payload",
                    fields=fields,
                    unresolved=False,
                    confidence=0.4,
                    notes=["Field names inferred from request.json/data access; types unknown."],
                )
            else:
                request_contract = _unresolved_contract(
                    "no JSON body keys inferred from Flask handler" if http_method != "GET" else "GET handler has no request body"
                )
            slug = _slugify(f"{Path(source.path).stem}-{action_name}-{http_method}")
            interfaces.append(
                CallableInterface(
                    id=f"python:{source.path}:{action_name}:{http_method}",
                    slug=slug,
                    stack="python",
                    framework="flask",
                    http_method=http_method,
                    route=route,
                    handler_symbol=action_name,
                    handler_path=source.path,
                    handler_line=_line_number(text, route_match.start()),
                    request=request_contract,
                    response=_unresolved_contract("Flask handler response shape is not statically typed"),
                    endpoint_env=_env_name(slug, "ENDPOINT"),
                    token_env=_env_name(slug, "TOKEN"),
                    side_effects="read" if http_method == "GET" else "unknown",
                    confidence=0.45 if not request_contract.unresolved else 0.35,
                    evidence=[f"{source.path}: {action_name} (@{route_match.group(1)}.route {http_method})"],
                )
            )
    return interfaces


def _detect_python(sources: list[_Source], index: dict[str, list[_TypeDef]]) -> list[CallableInterface]:
    interfaces: list[CallableInterface] = []
    for source in sources:
        if source.language != "Python":
            continue
        interfaces.extend(_detect_fastapi(source, index))
        interfaces.extend(_detect_flask(source, index))
    return interfaces


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def build_callable_capabilities(scan: ScanResult, root: Path) -> CallableCapabilitySet:
    """Detect callable HTTP interfaces from already-scanned source files."""
    project = root.name or "local-repository"
    sources: list[_Source] = []
    for record in scan.files:
        if record.role != "source" or record.language not in SOURCE_LANGUAGES:
            continue
        text = _safe_read(root, record.path)
        if not text:
            continue
        sources.append(_Source(path=record.path, language=record.language, text=text))

    index = _index_types(sources)
    interfaces: list[CallableInterface] = []
    interfaces.extend(_detect_dotnet_handlers(sources, index))
    interfaces.extend(_detect_dotnet_controllers(sources, index))
    interfaces.extend(_detect_java(sources, index))
    interfaces.extend(_detect_python(sources, index))

    deduped: dict[str, CallableInterface] = {}
    used_slugs: dict[str, int] = {}
    for interface in interfaces:
        if interface.id in deduped:
            continue
        base_slug = interface.slug
        count = used_slugs.get(base_slug, 0)
        if count:
            interface.slug = f"{base_slug}-{count + 1}"
            interface.endpoint_env = _env_name(interface.slug, "ENDPOINT")
            interface.token_env = _env_name(interface.slug, "TOKEN")
        used_slugs[base_slug] = count + 1
        deduped[interface.id] = interface

    ordered = sorted(deduped.values(), key=lambda item: (item.stack, item.handler_path, item.http_method, item.slug))
    notes: list[str] = []
    if not ordered:
        notes.append("No callable HTTP interfaces were detected in Java, Python, or .NET sources.")
    return CallableCapabilitySet(project=project, interfaces=ordered, notes=notes)
