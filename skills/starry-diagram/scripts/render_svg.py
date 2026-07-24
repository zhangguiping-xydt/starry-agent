from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    from common import parse_svg, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import parse_svg, write_json


def render_svg(source: Path, output: Path, report: Path | None = None) -> dict[str, object]:
    try:
        parse_svg(source)
    except Exception as exc:
        result: dict[str, object] = {
            "status": "failed",
            "renderer": "svg-copy",
            "source": str(source),
            "output": str(output),
            "error": str(exc),
        }
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        result = {
            "status": "passed",
            "renderer": "svg-copy",
            "source": str(source),
            "output": str(output),
        }
    if report is not None:
        write_json(report, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and copy semantic SVG source.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    result = render_svg(args.source, args.output, args.report)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
