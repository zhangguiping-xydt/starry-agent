from __future__ import annotations

import re


def derive_service_env_prefix(project_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(project_name).strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").upper()
    return cleaned or "LOCAL_REPOSITORY"


def service_env_names(env_prefix: str) -> dict[str, str]:
    return {
        "env_prefix": env_prefix,
        "base_url_env": env_prefix + "_BASE_URL",
        "token_env": env_prefix + "_TOKEN",
    }
