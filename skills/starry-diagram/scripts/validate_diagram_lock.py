from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, write_json

_REQUIRED_TOP_LEVEL_KEYS = (
    "id",
    "title",
    "type",
    "source_format",
    "canvas",
    "nodes",
    "edges",
    "style_tokens",
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _format_id(value: Any) -> str:
    return str(value) if value is not None else "<missing>"


def validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(lock, Mapping):
        return {"status": "failed", "errors": ["lock must be a mapping"], "warnings": warnings}

    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in lock:
            errors.append(f"missing required top-level key: {key}")

    canvas = lock.get("canvas")
    if not isinstance(canvas, Mapping):
        errors.append("canvas must be a mapping")
    else:
        for dimension in ("width", "height"):
            if not _is_int(canvas.get(dimension)):
                errors.append(f"canvas.{dimension} must be an int")

    nodes = lock.get("nodes")
    known_node_ids: set[str] = set()
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
    else:
        seen_node_ids: set[str] = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                errors.append(f"node at index {index} must be a mapping")
                continue

            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id:
                errors.append(f"node at index {index} must have an id")
            elif node_id in seen_node_ids:
                errors.append(f"duplicate node id: {node_id}")
            else:
                seen_node_ids.add(node_id)
                known_node_ids.add(node_id)

            label = node.get("label")
            if not isinstance(label, str) or not label:
                errors.append(f"node {_format_id(node_id)} must have a label")

    edges = lock.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be a list")
    else:
        seen_edge_ids: set[str] = set()
        for index, edge in enumerate(edges):
            if not isinstance(edge, Mapping):
                errors.append(f"edge at index {index} must be a mapping")
                continue

            edge_id_value = edge.get("id")
            edge_id = _format_id(edge_id_value)
            if not isinstance(edge_id_value, str) or not edge_id_value:
                errors.append(f"edge at index {index} must have an id")
            elif edge_id_value in seen_edge_ids:
                errors.append(f"duplicate edge id: {edge_id_value}")
            else:
                seen_edge_ids.add(edge_id_value)

            from_id = edge.get("from")
            to_id = edge.get("to")
            if not isinstance(from_id, str) or not from_id:
                errors.append(f"edge {edge_id} must have a source node")
            elif from_id not in known_node_ids:
                errors.append(f"edge {edge_id} references missing source node {from_id}")

            if not isinstance(to_id, str) or not to_id:
                errors.append(f"edge {edge_id} must have a target node")
            elif to_id not in known_node_ids:
                errors.append(f"edge {edge_id} references missing target node {to_id}")

    style_tokens = lock.get("style_tokens")
    if not isinstance(style_tokens, Mapping) or not style_tokens:
        errors.append("style_tokens must be a non-empty mapping")

    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings}


def validate_lock_file(path: Path) -> dict[str, Any]:
    return validate_lock(read_yaml(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_lock_file(args.lock_file)
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
