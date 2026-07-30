from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any


_TOKEN_RE = re.compile(
    r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
)
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_EDGE_KINDS = {"edge", "message", "relationship", "transition"}
_NODE_KINDS = {"node", "participant", "entity", "state"}
_GEOMETRY_TAGS = {"rect", "circle", "ellipse", "polygon", "path"}
_EPSILON = 1e-6
_ROUTE_ROLES = ("primary", "secondary", "control")
_BRANCH_NOTATION_ROLES = {"decision", "merge"}

Point = tuple[float, float]
Segment = tuple[Point, Point]
BBox = tuple[float, float, float, float]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numbers(value: str | None) -> list[float]:
    return [float(match.group(0)) for match in _NUMBER_RE.finditer(value or "")]


def _point_on_cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _point_on_quadratic(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0],
        u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1],
    )


def _curve_segments(points: list[Point]) -> list[Segment]:
    return list(zip(points, points[1:]))


def parse_path_segments(path_data: str | None, *, curve_steps: int = 12) -> tuple[list[Segment], bool]:
    tokens = _TOKEN_RE.findall(path_data or "")
    if not tokens:
        return [], False

    segments: list[Segment] = []
    current: Point = (0.0, 0.0)
    start: Point = current
    last_cubic_control: Point | None = None
    last_quadratic_control: Point | None = None
    previous_command: str | None = None
    command: str | None = None
    index = 0
    supported = True

    def is_command(value: str) -> bool:
        return len(value) == 1 and value.isalpha()

    def take(count: int) -> list[float] | None:
        nonlocal index
        if index + count > len(tokens) or any(is_command(value) for value in tokens[index : index + count]):
            return None
        values = [float(value) for value in tokens[index : index + count]]
        index += count
        return values

    def absolute(x: float, y: float, relative: bool) -> Point:
        return (current[0] + x, current[1] + y) if relative else (x, y)

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if command is None:
            return segments, False

        relative = command.islower()
        kind = command.upper()
        if kind == "Z":
            if current != start:
                segments.append((current, start))
            current = start
            previous_command = command
            command = None
            last_cubic_control = None
            last_quadratic_control = None
            continue

        if kind in {"M", "L", "T"}:
            values = take(2)
        elif kind == "H" or kind == "V":
            values = take(1)
        elif kind in {"S", "Q"}:
            values = take(4)
        elif kind == "C":
            values = take(6)
        elif kind == "A":
            values = take(7)
        else:
            return segments, False
        if values is None:
            return segments, False

        if kind == "M":
            current = absolute(values[0], values[1], relative)
            start = current
            command = "l" if relative else "L"
            last_cubic_control = None
            last_quadratic_control = None
        elif kind == "L":
            target = absolute(values[0], values[1], relative)
            segments.append((current, target))
            current = target
            last_cubic_control = None
            last_quadratic_control = None
        elif kind == "H":
            target = (current[0] + values[0], current[1]) if relative else (values[0], current[1])
            segments.append((current, target))
            current = target
            last_cubic_control = None
            last_quadratic_control = None
        elif kind == "V":
            target = (current[0], current[1] + values[0]) if relative else (current[0], values[0])
            segments.append((current, target))
            current = target
            last_cubic_control = None
            last_quadratic_control = None
        elif kind == "C":
            control1 = absolute(values[0], values[1], relative)
            control2 = absolute(values[2], values[3], relative)
            target = absolute(values[4], values[5], relative)
            points = [
                _point_on_cubic(current, control1, control2, target, step / curve_steps)
                for step in range(curve_steps + 1)
            ]
            segments.extend(_curve_segments(points))
            current = target
            last_cubic_control = control2
            last_quadratic_control = None
        elif kind == "S":
            if previous_command and previous_command.upper() in {"C", "S"} and last_cubic_control:
                control1 = (
                    2 * current[0] - last_cubic_control[0],
                    2 * current[1] - last_cubic_control[1],
                )
            else:
                control1 = current
            control2 = absolute(values[0], values[1], relative)
            target = absolute(values[2], values[3], relative)
            points = [
                _point_on_cubic(current, control1, control2, target, step / curve_steps)
                for step in range(curve_steps + 1)
            ]
            segments.extend(_curve_segments(points))
            current = target
            last_cubic_control = control2
            last_quadratic_control = None
        elif kind == "Q":
            control = absolute(values[0], values[1], relative)
            target = absolute(values[2], values[3], relative)
            points = [
                _point_on_quadratic(current, control, target, step / curve_steps)
                for step in range(curve_steps + 1)
            ]
            segments.extend(_curve_segments(points))
            current = target
            last_quadratic_control = control
            last_cubic_control = None
        elif kind == "T":
            if previous_command and previous_command.upper() in {"Q", "T"} and last_quadratic_control:
                control = (
                    2 * current[0] - last_quadratic_control[0],
                    2 * current[1] - last_quadratic_control[1],
                )
            else:
                control = current
            target = absolute(values[0], values[1], relative)
            points = [
                _point_on_quadratic(current, control, target, step / curve_steps)
                for step in range(curve_steps + 1)
            ]
            segments.extend(_curve_segments(points))
            current = target
            last_quadratic_control = control
            last_cubic_control = None
        elif kind == "A":
            target = absolute(values[5], values[6], relative)
            segments.append((current, target))
            current = target
            supported = False
            last_cubic_control = None
            last_quadratic_control = None

        previous_command = command

    return segments, supported and bool(segments)


def _segments_for_element(element: Any) -> tuple[list[Segment], bool]:
    if element.attrib.get("transform"):
        return [], False
    tag = _local_name(element.tag)
    if tag == "line":
        values = [element.attrib.get(name) for name in ("x1", "y1", "x2", "y2")]
        if any(value is None for value in values):
            return [], False
        points = [float(value) for value in values]
        return [((points[0], points[1]), (points[2], points[3]))], True
    if tag == "polyline":
        values = _numbers(element.attrib.get("points"))
        if len(values) < 4 or len(values) % 2:
            return [], False
        points = list(zip(values[::2], values[1::2]))
        return _curve_segments(points), True
    if tag == "path":
        return parse_path_segments(element.attrib.get("d"))
    return [], False


def _bbox_for_element(element: Any) -> BBox | None:
    if element.attrib.get("transform"):
        return None
    tag = _local_name(element.tag)
    try:
        if tag == "rect":
            x = float(element.attrib.get("x", 0))
            y = float(element.attrib.get("y", 0))
            width = float(element.attrib["width"])
            height = float(element.attrib["height"])
            return x, y, x + width, y + height
        if tag == "circle":
            cx = float(element.attrib["cx"])
            cy = float(element.attrib["cy"])
            radius = float(element.attrib["r"])
            return cx - radius, cy - radius, cx + radius, cy + radius
        if tag == "ellipse":
            cx = float(element.attrib["cx"])
            cy = float(element.attrib["cy"])
            rx = float(element.attrib["rx"])
            ry = float(element.attrib["ry"])
            return cx - rx, cy - ry, cx + rx, cy + ry
        if tag == "polygon":
            values = _numbers(element.attrib.get("points"))
            if len(values) < 6 or len(values) % 2:
                return None
            xs = values[::2]
            ys = values[1::2]
            return min(xs), min(ys), max(xs), max(ys)
        if tag == "path":
            segments, _ = parse_path_segments(element.attrib.get("d"))
            if not segments:
                return None
            points = [point for segment in segments for point in segment]
            return (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            )
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _semantic_element_geometry(element: Any) -> tuple[list[Segment], bool]:
    if element.attrib.get("transform"):
        return [], False
    candidates = [
        child
        for child in element.iter()
        if child is not element and _local_name(child.tag) in {"line", "polyline", "path"}
    ]
    for candidate in candidates:
        segments, supported = _segments_for_element(candidate)
        if segments:
            return segments, supported
    return [], False


def _semantic_element_bbox(element: Any) -> BBox | None:
    if element.attrib.get("transform"):
        return None
    boxes = [
        box
        for child in element.iter()
        if child is not element and _local_name(child.tag) in _GEOMETRY_TAGS
        if (box := _bbox_for_element(child)) is not None
    ]
    if not boxes:
        return None
    return max(boxes, key=lambda box: max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1]))


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_intersection(first: Segment, second: Segment) -> bool:
    a, b = first
    c, d = second
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    return (
        ((o1 > _EPSILON and o2 < -_EPSILON) or (o1 < -_EPSILON and o2 > _EPSILON))
        and ((o3 > _EPSILON and o4 < -_EPSILON) or (o3 < -_EPSILON and o4 > _EPSILON))
    )


def _segment_intersects_box(segment: Segment, box: BBox) -> bool:
    (x0, y0), (x1, y1) = segment
    left, top, right, bottom = box
    if right - left <= 1 or bottom - top <= 1:
        return False
    left += 0.5
    top += 0.5
    right -= 0.5
    bottom -= 0.5
    dx = x1 - x0
    dy = y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - left, right - x0, y0 - top, bottom - y0)
    lower = 0.0
    upper = 1.0
    for pi, qi in zip(p, q):
        if abs(pi) <= _EPSILON:
            if qi < 0:
                return False
            continue
        ratio = qi / pi
        if pi < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return upper >= 0 and lower <= 1


def _length(segments: list[Segment]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segments)


def _route_mode(element: Any, segments: list[Segment]) -> str:
    candidates = [
        child
        for child in element.iter()
        if child is not element and _local_name(child.tag) in {"line", "polyline", "path"}
    ]
    if not candidates:
        return "unknown"
    candidate = candidates[0]
    tag = _local_name(candidate.tag)
    if tag == "line":
        return "straight"
    if tag == "path" and re.search(r"[AaCcQqSsTt]", candidate.attrib.get("d", "")):
        return "curved"
    simplified = _simplify_segments(segments)
    if len(simplified) <= 1:
        return "straight"
    if all(
        abs(end[0] - start[0]) <= _EPSILON
        or abs(end[1] - start[1]) <= _EPSILON
        for start, end in simplified
    ):
        return "orthogonal"
    return "polyline"


def _simplify_segments(segments: list[Segment]) -> list[Segment]:
    simplified: list[Segment] = []
    for start, end in segments:
        if math.hypot(end[0] - start[0], end[1] - start[1]) <= _EPSILON:
            continue
        if not simplified:
            simplified.append((start, end))
            continue
        previous_start, previous_end = simplified[-1]
        first = (previous_end[0] - previous_start[0], previous_end[1] - previous_start[1])
        second = (end[0] - start[0], end[1] - start[1])
        cross = first[0] * second[1] - first[1] * second[0]
        dot = first[0] * second[0] + first[1] * second[1]
        contiguous = math.hypot(previous_end[0] - start[0], previous_end[1] - start[1]) <= 1e-3
        if contiguous and abs(cross) <= 1e-3 and dot > 0:
            simplified[-1] = (previous_start, end)
        else:
            simplified.append((start, end))
    return simplified


def _expanded_box(box: BBox, clearance: float) -> BBox:
    return (
        box[0] - clearance,
        box[1] - clearance,
        box[2] + clearance,
        box[3] + clearance,
    )


def _role_limits(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        role: float(limit)
        for role in _ROUTE_ROLES
        if isinstance((limit := value.get(role)), int | float)
        and not isinstance(limit, bool)
    }


def _edge_role_map(edge_roles: Any) -> dict[str, str]:
    if not isinstance(edge_roles, Mapping):
        return {}
    result: dict[str, str] = {}
    for role in _ROUTE_ROLES:
        values = edge_roles.get(role)
        if not isinstance(values, list):
            continue
        for edge_id in values:
            if isinstance(edge_id, str) and edge_id:
                result[edge_id] = role
    return result


def _route_economy(
    edges: Mapping[str, dict[str, Any]],
    nodes: Mapping[str, BBox],
    node_roles: Mapping[str, str],
    policy: Any,
    *,
    edge_roles: Any = None,
    primary_items: Any = None,
    allow_backward_detours: bool = False,
    routing_family: str = "axis",
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(policy, Mapping) or policy.get("direct_when_clear") is not True:
        return {"checked": False}, []

    clearance_value = policy.get("direct_path_clearance_px", 0)
    clearance = (
        float(clearance_value)
        if isinstance(clearance_value, int | float) and not isinstance(clearance_value, bool)
        else 0.0
    )
    alignment_value = policy.get("axis_alignment_tolerance_px", 0)
    alignment_tolerance = (
        float(alignment_value)
        if isinstance(alignment_value, int | float)
        and not isinstance(alignment_value, bool)
        else 0.0
    )
    aligned_detour_limits = _role_limits(
        policy.get("max_axis_aligned_detour_ratio")
    )
    aligned_bend_limits = _role_limits(policy.get("max_axis_aligned_bends"))
    clear_detour_limits = _role_limits(policy.get("max_clear_detour_ratio"))
    clear_bend_limits = _role_limits(policy.get("max_clear_bends"))
    total_detour_limits = _role_limits(policy.get("max_total_detour_ratio"))
    total_bend_limits = _role_limits(policy.get("max_total_bends"))
    roles = _edge_role_map(edge_roles)
    primary_order = {
        item_id: index
        for index, item_id in enumerate(primary_items if isinstance(primary_items, list) else [])
        if isinstance(item_id, str)
    }

    metrics: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    errors: list[str] = []
    for edge_id, edge in edges.items():
        segments = edge["segments"]
        simplified = _simplify_segments(segments)
        if not simplified:
            continue
        start = simplified[0][0]
        end = simplified[-1][1]
        direct_length = math.hypot(end[0] - start[0], end[1] - start[1])
        actual_length = _length(segments)
        detour_ratio = actual_length / direct_length if direct_length > _EPSILON else 1.0
        route_mode = edge.get("route_mode", "unknown")
        bend_count = None if route_mode == "curved" else max(0, len(simplified) - 1)
        endpoints = {edge.get("from"), edge.get("to")}
        direct_segment = (start, end)
        blockers = sorted(
            node_id
            for node_id, box in nodes.items()
            if node_id not in endpoints
            and _segment_intersects_box(direct_segment, _expanded_box(box, clearance))
        )
        role = roles.get(edge_id, "secondary")
        source = edge.get("from")
        target = edge.get("to")
        backward = (
            allow_backward_detours
            and isinstance(source, str)
            and isinstance(target, str)
            and source in primary_order
            and target in primary_order
            and primary_order[target] <= primary_order[source]
        )
        exempt_from_direct = role == "control" or source == target or backward
        direct_clear = not blockers and direct_length > _EPSILON
        delta_x = abs(end[0] - start[0])
        delta_y = abs(end[1] - start[1])
        axis_aligned = (
            delta_x <= alignment_tolerance or delta_y <= alignment_tolerance
        )
        source_role = node_roles.get(source, "") if isinstance(source, str) else ""
        target_role = node_roles.get(target, "") if isinstance(target, str) else ""
        branch_endpoint = bool(
            {source_role, target_role} & _BRANCH_NOTATION_ROLES
        )
        diagonal_allowed = routing_family in {"radial", "loop"} or (
            routing_family == "branching" and branch_endpoint
        )
        edge_violations: list[str] = []

        total_ratio_limit = total_detour_limits.get(role)
        if total_ratio_limit is not None and detour_ratio > total_ratio_limit:
            edge_violations.append("excessive-detour")
            errors.append(
                f"EXCESSIVE_EDGE_DETOUR: edge {edge_id} route is {detour_ratio:.2f}x "
                f"the direct distance, maximum for {role} edges is {total_ratio_limit:g}x"
            )
        total_bend_limit = total_bend_limits.get(role)
        if (
            total_bend_limit is not None
            and bend_count is not None
            and bend_count > total_bend_limit
        ):
            edge_violations.append("excessive-bends")
            errors.append(
                f"EXCESSIVE_EDGE_BENDS: edge {edge_id} has {bend_count} bend(s), "
                f"maximum for {role} edges is {int(total_bend_limit)}"
            )

        if (
            not axis_aligned
            and not exempt_from_direct
            and not diagonal_allowed
            and route_mode not in {"orthogonal", "unknown"}
        ):
            edge_violations.append("routing-rhythm")
            errors.append(
                f"DIAGONAL_ROUTE_BREAKS_RHYTHM: edge {edge_id} uses {route_mode} "
                f"routing in the {routing_family} routing family; use a minimal "
                "orthogonal connector or align the endpoints"
            )

        if direct_clear and not exempt_from_direct:
            clear_ratio_limit = (
                aligned_detour_limits.get(role)
                if axis_aligned
                else clear_detour_limits.get(role)
            )
            if clear_ratio_limit is not None and detour_ratio > clear_ratio_limit:
                edge_violations.append("clear-path-detour")
                errors.append(
                    f"UNNECESSARY_DETOUR: edge {edge_id} has a clear economical route but is "
                    f"{detour_ratio:.2f}x the endpoint distance; maximum is "
                    f"{clear_ratio_limit:g}x"
                )
            clear_bend_limit = (
                aligned_bend_limits.get(role)
                if axis_aligned
                else clear_bend_limits.get(role)
            )
            if (
                clear_bend_limit is not None
                and bend_count is not None
                and bend_count > clear_bend_limit
            ):
                edge_violations.append("clear-path-bends")
                errors.append(
                    f"UNNECESSARY_DETOUR: edge {edge_id} has a clear economical route but uses "
                    f"{bend_count} bend(s); maximum is {int(clear_bend_limit)}"
                )

        record = {
            "edge": edge_id,
            "role": role,
            "route_mode": route_mode,
            "bend_count": bend_count,
            "detour_ratio": round(detour_ratio, 3),
            "direct_clear": direct_clear,
            "direct_blockers": blockers,
            "axis_aligned": axis_aligned,
            "routing_family": routing_family,
            "source_notation_role": source_role,
            "target_notation_role": target_role,
            "diagonal_allowed": diagonal_allowed,
            "backward_feedback": backward,
            "direct_rule_exempt": exempt_from_direct,
        }
        metrics.append(record)
        if edge_violations:
            violations.append({**record, "reasons": edge_violations})

    return {
        "checked": True,
        "policy": dict(policy),
        "edges": metrics,
        "violations": violations,
    }, errors


def analyze_visual_geometry(
    root: Any,
    viewbox: tuple[float, float, float, float],
    limits: Mapping[str, Any],
    *,
    edge_roles: Any = None,
    primary_items: Any = None,
    allow_backward_detours: bool = False,
    routing_family: str = "axis",
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    edges: dict[str, dict[str, Any]] = {}
    nodes: dict[str, BBox] = {}
    node_roles: dict[str, str] = {}

    for element in root.iter():
        item_id = element.attrib.get("data-diagram-id")
        kind = element.attrib.get("data-diagram-kind")
        if not item_id or not kind:
            continue
        if kind in _EDGE_KINDS:
            segments, supported = _semantic_element_geometry(element)
            edges[item_id] = {
                "from": element.attrib.get("data-from"),
                "to": element.attrib.get("data-to"),
                "segments": segments,
                "supported": supported,
                "route_mode": _route_mode(element, segments),
            }
        elif kind in _NODE_KINDS:
            box = _semantic_element_bbox(element)
            if box is not None:
                nodes[item_id] = box
                node_roles[item_id] = element.attrib.get("data-notation-role", "")

    analyzed_edges = {
        item_id: edge
        for item_id, edge in edges.items()
        if edge["supported"] and edge["segments"]
    }
    edge_fraction = len(analyzed_edges) / len(edges) if edges else 1.0
    minimum_fraction = limits.get("min_analyzable_edge_fraction", 0.0)
    if isinstance(minimum_fraction, int | float) and edge_fraction < float(minimum_fraction):
        errors.append(
            f"visual geometry analyzes {edge_fraction:.0%} of edges, below required "
            f"{float(minimum_fraction):.0%}; avoid unsupported transforms or arc-only routes"
        )
    elif len(analyzed_edges) < len(edges):
        warnings.append(
            f"visual geometry skipped {len(edges) - len(analyzed_edges)} unsupported edge(s)"
        )

    crossings: list[dict[str, str]] = []
    edge_ids = sorted(analyzed_edges)
    for index, first_id in enumerate(edge_ids):
        first = analyzed_edges[first_id]
        for second_id in edge_ids[index + 1 :]:
            second = analyzed_edges[second_id]
            if {first.get("from"), first.get("to")} & {second.get("from"), second.get("to")}:
                continue
            if any(
                _proper_intersection(first_segment, second_segment)
                for first_segment in first["segments"]
                for second_segment in second["segments"]
            ):
                crossings.append({"first": first_id, "second": second_id})

    max_crossings = limits.get("max_edge_crossings")
    if isinstance(max_crossings, int) and len(crossings) > max_crossings:
        errors.append(
            f"visual geometry has {len(crossings)} edge crossing(s), maximum is {max_crossings}"
        )

    node_intersections: list[dict[str, str]] = []
    for edge_id, edge in analyzed_edges.items():
        endpoints = {edge.get("from"), edge.get("to")}
        for node_id, box in nodes.items():
            if node_id in endpoints:
                continue
            if any(_segment_intersects_box(segment, box) for segment in edge["segments"]):
                node_intersections.append({"edge": edge_id, "node": node_id})

    max_node_intersections = limits.get("max_edge_node_intersections")
    if isinstance(max_node_intersections, int) and len(node_intersections) > max_node_intersections:
        errors.append(
            f"visual geometry has {len(node_intersections)} edge-to-nonendpoint-node "
            f"intersection(s), maximum is {max_node_intersections}"
        )

    diagonal = math.hypot(viewbox[2], viewbox[3])
    max_long_ratio = limits.get("max_long_edge_ratio")
    long_edges: list[dict[str, Any]] = []
    if isinstance(max_long_ratio, int | float) and diagonal > 0:
        for edge_id, edge in analyzed_edges.items():
            ratio = _length(edge["segments"]) / diagonal
            if ratio > float(max_long_ratio):
                long_edges.append({"edge": edge_id, "ratio": round(ratio, 3)})
        if long_edges:
            errors.append(
                f"visual geometry has {len(long_edges)} edge(s) longer than "
                f"{float(max_long_ratio):g} canvas diagonals"
            )

    route_economy, route_errors = _route_economy(
        analyzed_edges,
        nodes,
        node_roles,
        limits.get("route_economy"),
        edge_roles=edge_roles,
        primary_items=primary_items,
        allow_backward_detours=allow_backward_detours,
        routing_family=routing_family,
    )
    errors.extend(route_errors)

    report = {
        "coverage": {
            "edges_total": len(edges),
            "edges_analyzed": len(analyzed_edges),
            "edge_fraction": round(edge_fraction, 4),
            "nodes_total": sum(
                1
                for element in root.iter()
                if element.attrib.get("data-diagram-kind") in _NODE_KINDS
            ),
            "nodes_bounded": len(nodes),
        },
        "limits": dict(limits),
        "edge_crossings": crossings,
        "edge_node_intersections": node_intersections,
        "long_edges": long_edges,
        "route_economy": route_economy,
    }
    return report, errors, warnings
