from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_layout_catalogue(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Layout registry not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    if not isinstance(registry, dict):
        raise ValueError("Layout registry must be a dictionary.")

    if "layouts" not in registry:
        raise ValueError("Layout registry must contain a top-level 'layouts' key.")

    return registry