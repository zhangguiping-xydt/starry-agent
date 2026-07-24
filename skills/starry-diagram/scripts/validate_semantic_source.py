from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    from common import parse_svg, read_yaml, semantic_items, svg_semantic_elements, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_svg, read_yaml, semantic_items, svg_semantic_elements, write_json


def _graphviz_has_id(source_text: str, item_id: str) -> bool:
    pattern = re.compile(rf"\bid\s*=\s*([\"']){re.escape(item_id)}\1")
    return pattern.search(source_text) is not None


def _source_has_id(
    source_format: str,
    source_text: str,
    source_path: Path,
    item_id: str,
) -> bool:
    if source_format == "graphviz":
        return _graphviz_has_id(source_text, item_id)
    if source_format == "svg":
        try:
            return item_id in svg_semantic_elements(parse_svg(source_path))
        except Exception:
            return False
    return f"diagram-id:{item_id}" in source_text


def validate_semantic(
    lock: dict[str, Any],
    source_text: str,
    *,
    source_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    source_format = lock.get("source_format")
    if not isinstance(source_format, str):
        source_format = ""

    items = semantic_items(lock)
    verified_ids: list[str] = []
    for item in items:
        item_id = item["id"]
        label = item.get("label")
        if label and label not in source_text:
            errors.append(f"missing required semantic label for {item_id}: {label}")
        if not _source_has_id(source_format, source_text, source_path, item_id):
            marker_hint = (
                f'id="{item_id}"'
                if source_format in {"graphviz", "svg"}
                else f"diagram-id:{item_id} comment marker"
            )
            errors.append(f"missing stable semantic id {item_id}; expected {marker_hint}")
        else:
            verified_ids.append(item_id)

    return {
        "status": "failed" if errors else "passed",
        "semantic": {
            "errors": errors,
            "warnings": warnings,
            "expected_ids": len(items),
            "verified_ids": len(verified_ids),
        },
    }


def validate_semantic_source(lock_path: Path, source_path: Path) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    source_text = source_path.read_text(encoding="utf-8")
    return validate_semantic(lock, source_text, source_path=source_path)


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
