from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_text = str(REPO_ROOT)
if sys.path[0] != repo_root_text:
    try:
        sys.path.remove(repo_root_text)
    except ValueError:
        pass
    sys.path.insert(0, repo_root_text)
