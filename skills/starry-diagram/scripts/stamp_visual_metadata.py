from __future__ import annotations

import argparse
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

try:
    from common import parse_svg, read_yaml, semantic_items, svg_semantic_elements, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_svg, read_yaml, semantic_items, svg_semantic_elements, write_json


def stamp_visual_metadata(lock_path: Path, svg_path: Path, output_path: Path) -> dict[str, object]:
    lock = read_yaml(lock_path)
    root = parse_svg(svg_path)
    elements = svg_semantic_elements(root)
    missing: list[str] = []
    stamped: list[str] = []

    for item in semantic_items(lock):
        item_id = item["id"]
        element = elements.get(item_id)
        if element is None:
            missing.append(item_id)
            continue
        element.set("data-diagram-id", item_id)
        element.set("data-diagram-kind", item["kind"])
        if item.get("from"):
            element.set("data-from", item["from"])
        if item.get("to"):
            element.set("data-to", item["to"])
        if item["kind"] in {"group", "lane"}:
            record = next(
                (
                    value
                    for value in lock.get(item["section"], [])
                    if isinstance(value, Mapping) and value.get("id") == item_id
                ),
                None,
            )
            if record is not None:
                element.set(
                    "data-members",
                    ",".join(str(value) for value in record.get("members", [])),
                )
        stamped.append(item_id)

    result: dict[str, object] = {
        "status": "failed" if missing else "passed",
        "source": str(svg_path),
        "output": str(output_path),
        "stamped": sorted(stamped),
        "missing": sorted(missing),
    }
    if missing:
        return result

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        ET.ElementTree(root).write(handle, encoding="utf-8", xml_declaration=True)
    os.replace(temporary_path, output_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stamp locked semantic metadata into visual SVG.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("svg_file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    output = args.output or args.svg_file
    report = stamp_visual_metadata(args.lock_file, args.svg_file, output)
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
