from __future__ import annotations

from typing import Any


def resolve_visual_family(modality: str, registry: dict[str, Any]) -> str:
    selection_bias = registry.get("selection_bias", {})
    default_family_by_modality = selection_bias.get("default_family_by_modality", {})

    family = default_family_by_modality.get(modality)
    if family:
        return family

    fallback_order = selection_bias.get("fallback_family_order", [])
    if fallback_order:
        return fallback_order[0]

    raise ValueError(
        f"No visual family mapping found for modality '{modality}' "
        "and no fallback family order configured."
    )


def get_family_layouts(
    family_name: str,
    registry: dict[str, Any],
    automation_statuses: tuple[str, ...] = ("safe", "partial"),
) -> list[dict[str, Any]]:
    families = registry.get("visual_families", {})
    family = families.get(family_name)

    if not family:
        raise ValueError(f"Visual family '{family_name}' not found in registry.")

    layouts = family.get("layouts", [])
    filtered = [
        layout
        for layout in layouts
        if layout.get("automation_status") in automation_statuses
    ]

    return sorted(filtered, key=lambda x: x.get("priority", 999))