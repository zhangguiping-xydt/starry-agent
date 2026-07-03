from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "security.md",
    REPO_ROOT / "docs" / "skill-output-format.md",
    REPO_ROOT / "docs" / "compatibility.md",
    REPO_ROOT / "docs" / "evals.md",
    REPO_ROOT / "adapters" / "README.md",
    REPO_ROOT / "adapters" / "generic-markdown" / "README.md",
    REPO_ROOT / "adapters" / "cli-workflow" / "README.md",
]
REQUIRED_PHRASES = [
    "local-first",
    "local scanning",
    "does not upload source code",
    "does not require a remote database",
    "does not use a vector database by default",
    "analyze/generate output must be outside the target repository",
    "helper scripts are read-only",
    "no network",
    "no dependency installation",
    "generated helpers do not spawn shell commands",
    "Callable helper scripts can use live HTTP only after explicit endpoint configuration and --execute",
    "artifact chain",
    "capability evidence",
    "capability graph",
    "skill spec",
    "verification report",
    "adapter contract",
    "AI coding agent",
    "CapabilityRegistry/FastAPI/runtime hot registration",
    "multi-agent-dev external_skills hot loading",
]
FORBIDDEN_TEXT = [
    "/media/private",
    "/home/example",
    "private token",
    "private evidence path",
    "evidence path:",
]


def test_published_skill_catalog_includes_starry_diagram() -> None:
    skill_path = REPO_ROOT / "skills" / "starry-diagram" / "SKILL.md"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert skill_path.is_file()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "name: starry-diagram" in skill_text
    assert "skills/starry-diagram/" in readme
    assert "skills/starry-diagram/" in readme_zh


def test_public_docs_exist_and_state_required_boundaries() -> None:
    combined = ""
    for path in DOC_PATHS:
        assert path.is_file(), f"missing document: {path.name}"
        combined += "\n" + path.read_text(encoding="utf-8")

    normalized = combined.lower()
    for phrase in REQUIRED_PHRASES:
        assert phrase.lower() in normalized, phrase


def test_public_docs_do_not_contain_private_paths_or_tokens() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS if path.exists())

    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in combined
