from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from common import colors_in_text, locked_colors, parse_svg, read_yaml, required_node_labels, svg_text_content, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import colors_in_text, locked_colors, parse_svg, read_yaml, required_node_labels, svg_text_content, write_json


def validate_visual(lock: dict[str, Any], svg_text: str, svg_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        root = parse_svg(svg_path)
    except Exception as exc:
        errors.append(str(exc))
        return {
            "status": "failed",
            "visual": {"errors": errors, "warnings": warnings},
        }

    if root.attrib.get("viewBox") is None:
        errors.append("visual.svg missing viewBox")

    text_content = svg_text_content(root)
    for label in required_node_labels(lock):
        if label not in text_content:
            errors.append(f"missing required visual label: {label}")

    allowed_colors = locked_colors(lock)
    for color in sorted(colors_in_text(svg_text)):
        if color not in allowed_colors:
            errors.append(f"visual.svg uses color outside style_tokens: {color}")

    return {
        "status": "failed" if errors else "passed",
        "visual": {"errors": errors, "warnings": warnings},
    }


def validate_visual_svg(lock_path: Path, svg_path: Path) -> dict[str, Any]:
    lock = read_yaml(lock_path)
    svg_text = svg_path.read_text(encoding="utf-8")
    return validate_visual(lock, svg_text, svg_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a starry diagram SVG against a lock file.")
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("svg_file", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = validate_visual_svg(args.lock_file, args.svg_file)
    if args.report is not None:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
