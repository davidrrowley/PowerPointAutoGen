from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_layout_catalogue(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Visual family registry not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    if not isinstance(registry, dict):
        raise ValueError("Visual family registry must be a dictionary.")

    if "visual_families" not in registry:
        raise ValueError(
            "Visual family registry must contain a top-level 'visual_families' key."
        )

    return registry