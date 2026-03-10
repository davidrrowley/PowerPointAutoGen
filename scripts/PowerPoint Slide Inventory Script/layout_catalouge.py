from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_layout_catalogue(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Layout catalogue not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        catalogue = yaml.safe_load(f)

    if not isinstance(catalogue, dict):
        raise ValueError("Layout catalogue must be a dictionary.")

    if "patterns" not in catalogue or "modality_preferences" not in catalogue:
        raise ValueError("Layout catalogue must contain 'patterns' and 'modality_preferences'.")

    return catalogue
