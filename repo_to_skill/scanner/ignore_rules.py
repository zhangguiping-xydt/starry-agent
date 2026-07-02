from __future__ import annotations

from pathlib import Path

DEFAULT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".runs",
    ".claude",
    ".vs",
    "graphify-out",
    "Artifacts",
    "node_modules",
    "bin",
    "obj",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    ".tmp",
    "tmp",
    "bundles",
    ".gradle",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".expo",
    ".idea",
    ".vscode",
}

SENSITIVE_FILENAMES = {
    ".env",
    ".envrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "private_key",
    "credentials.json",
    "secrets.json",
    "service-account.json",
}

SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}


def should_skip_dir(path: Path) -> bool:
    return path.name in DEFAULT_SKIP_DIRS


def is_sensitive_file(path: Path) -> bool:
    name = path.name.lower()
    # Catch dotted .env variants (.env.local, .env.production, ...) that hold
    # real secrets, not just the bare ".env".
    if name in SENSITIVE_FILENAMES or name.startswith(".env."):
        return True
    return any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)
