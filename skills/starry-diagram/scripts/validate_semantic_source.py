from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from common import read_yaml, required_node_labels, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import read_yaml, required_node_labels, write_json


def _format_id(value: Any) -> str:
    return str(value) if value is not None else "<missing>"


def validate_semantic(lock: dict[str, Any], source_text: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    for label in required_node_labels(lock):
        if label not in source_text:
            errors.append(f"missing required node label: {label}")

    edges = lock.get("edges", [])
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue

            edge_id = _format_id(edge.get("id"))
            source = edge.get("from")
            target = edge.get("to")
            label = edge.get("label")

            if isinstance(source, str) and source not in source_text:
                errors.append(f"missing edge source id for {edge_id}: {source}")
            if isinstance(target, str) and target not in source_text:
                errors.append(f"missing edge target id for {edge_id}: {target}")
            if isinstance(label, str) and label not in source_text:
                warnings.append(f"edge label not found in source for {edge_id}: {label}")

    return {
        "status": "failed" if errors else "passed",
        "semantic": {"errors": errors, "warnings": warnings},
    }


def validate_semantic_source(lock_path: Path, source_path: Path) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    source_text = source_path.read_text(encoding="utf-8")
    return validate_semantic(lock, source_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram source against a lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("source_file", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_semantic_source(args.lock_file, args.source_file)
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
