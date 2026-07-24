from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from common import command_available, run_command, write_json
except ModuleNotFoundError:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from common import command_available, run_command, write_json


def _write_report(report: Path | None, result: dict[str, object]) -> None:
    if report is not None:
        write_json(report, result)


def render_mermaid(source: Path, output: Path, report: Path | None = None) -> dict[str, object]:
    if not command_available("mmdc"):
        result: dict[str, object] = {
            "status": "render_unavailable",
            "renderer": "mmdc",
            "source": str(source),
            "output": str(output),
        }
        _write_report(report, result)
        return result

    output.parent.mkdir(parents=True, exist_ok=True)
    process = run_command(["mmdc", "-i", str(source), "-o", str(output)])
    result = {
        "status": "passed" if process.returncode == 0 else "failed",
        "renderer": "mmdc",
        "source": str(source),
        "output": str(output),
        "returncode": process.returncode,
    }
    if process.returncode != 0:
        result["stderr"] = process.stderr
    _write_report(report, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Mermaid diagram to SVG.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    result = render_mermaid(args.source, args.output, args.report)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
