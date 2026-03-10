from __future__ import annotations

from pptx import Presentation


def find_layout_by_name(prs: Presentation, layout_name: str):
    for layout in prs.slide_layouts:
        if layout.name.strip().lower() == layout_name.strip().lower():
            return layout

    available = [layout.name for layout in prs.slide_layouts]
    raise ValueError(
        f"Layout '{layout_name}' not found. Available layouts: {available}"
    )