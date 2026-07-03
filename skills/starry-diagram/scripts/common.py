from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def node_ids(lock: dict[str, Any]) -> set[str]:
    nodes = lock.get("nodes", [])
    if not isinstance(nodes, list):
        return set()
    return {node["id"] for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), str)}


def required_node_labels(lock: dict[str, Any]) -> list[str]:
    nodes = lock.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    labels: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        label = node.get("label")
        if node.get("required") is True and isinstance(label, str):
            labels.append(label)
    return labels


def locked_colors(lock: dict[str, Any]) -> set[str]:
    tokens = lock.get("style_tokens", {})
    colors: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            colors.update(color.upper() for color in colors_in_text(value))
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(tokens)
    return colors


def colors_in_text(text: str) -> set[str]:
    return {match.group(0).upper() for match in _COLOR_RE.finditer(text)}


def parse_svg(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


_NON_VISIBLE_TEXT_TAGS = {"metadata", "style", "script", "defs", "title", "desc"}


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def svg_text_content(root: ET.Element) -> str:
    parts: list[str] = []

    def collect(element: ET.Element) -> None:
        if _local_name(element.tag) in _NON_VISIBLE_TEXT_TAGS:
            if element.tail:
                parts.append(element.tail)
            return
        if element.text:
            parts.append(element.text)
        for child in element:
            collect(child)
        if element.tail:
            parts.append(element.tail)

    collect(root)
    return "".join(parts)


def has_viewbox(root: ET.Element) -> bool:
    return "viewBox" in root.attrib


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
