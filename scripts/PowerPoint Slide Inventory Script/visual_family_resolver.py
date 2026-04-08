from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _load_registry() -> dict[str, Any]:
    registry_path = Path(__file__).resolve().parent / "visual_family_registry.yaml"
    with registry_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_visual_family(modality: str, registry: dict[str, Any] | None = None) -> str:
    if registry is None:
        registry = _load_registry()
    selection_bias = registry.get("selection_bias", {})
    default_map = selection_bias.get("default_family_by_modality", {})
    if modality in default_map:
        return default_map[modality]
    fallback_order = selection_bias.get("fallback_family_order", [])
    families = registry.get("visual_families", {})
    for family_name in fallback_order:
        if family_name in families:
            return family_name
    if families:
        return next(iter(families))
    raise ValueError(
        f"Cannot resolve a visual family for modality '{modality}'. "
        f"No mapping found and no fallback families available."
    )


def get_family_layouts(family_name: str, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if registry is None:
        registry = _load_registry()
    families = registry.get("visual_families", {})
    if family_name not in families:
        raise ValueError(
            f"Visual family '{family_name}' not found in registry. "
            f"Available families: {list(families.keys())}"
        )
    return families[family_name].get("layouts", [])


def _matches_title_slide(fields: dict[str, Any]) -> bool:
    return "title" in fields


def _matches_index_slide(fields: dict[str, Any]) -> bool:
    return "title" in fields and "sections" in fields


def _matches_closing_slide(fields: dict[str, Any]) -> bool:
    return "title" in fields or "contact" in fields


def _matches_simple_body(fields: dict[str, Any]) -> bool:
    return "body" in fields


def _matches_two_column(fields: dict[str, Any]) -> bool:
    return "body_left" in fields and "body_right" in fields


def _matches_boxes(fields: dict[str, Any]) -> bool:
    return "intro" in fields and "boxes" in fields


def _matches_four_points(fields: dict[str, Any]) -> bool:
    return (
        "points" in fields
        and isinstance(fields["points"], list)
        and len(fields["points"]) == 4
    )


def _matches_half_image(fields: dict[str, Any]) -> bool:
    return "image" in fields and (
        "body" in fields or ("lead" in fields and "proof_points" in fields)
    )


def _matches_fact(fields: dict[str, Any]) -> bool:
    return "body" in fields or ("lead" in fields and "proof_points" in fields)


def _matches_case_study(fields: dict[str, Any]) -> bool:
    return "body_left" in fields and "body_right" in fields and "image" in fields


def _matches_table_like(fields: dict[str, Any]) -> bool:
    return "body" in fields or "table_rows" in fields


def _layout_matches_fields(layout_id: str, fields: dict[str, Any]) -> bool:
    if layout_id in {"title_slide", "cover_image_1", "cover_image_2", "cover_image_7", "cover_image_8"}:
        return _matches_title_slide(fields)

    if layout_id == "index_slide":
        return _matches_index_slide(fields)

    if layout_id == "thank_you":
        return _matches_closing_slide(fields)

    if layout_id == "big_text":
        return "title" in fields and "body" not in fields and "image" not in fields

    if layout_id == "quote_layout":
        return "quote" in fields or "title" in fields

    if layout_id == "divider_standard":
        return "title" in fields

    if layout_id == "divider_with_contents":
        return "title" in fields

    if layout_id in {"ibm_sign_off_blue80", "ibm_sign_off_blue60", "ibm_sign_off_black"}:
        return True

    if layout_id in {"title_text", "title_text_split_background"}:
        return _matches_simple_body(fields)

    if layout_id in {
        "title_text_two_columns",
        "title_text_two_columns_diff",
        "title_text_two_narrow_columns",
    }:
        return _matches_two_column(fields)

    if layout_id == "insight_text_boxes":
        return _matches_boxes(fields)

    if layout_id == "title_text_four_columns":
        return _matches_four_points(fields)

    if layout_id in {
        "title_text_half_image",
        "fact_number_half_image",
        "title_image",
        "title_gray_box_over_images",
        "text_gray_box_over_images",
    }:
        return _matches_half_image(fields)

    if layout_id == "fact_number":
        return _matches_fact(fields)

    if layout_id in {"case_study_1", "case_study_2"}:
        return _matches_case_study(fields)

    if layout_id == "table":
        return _matches_table_like(fields)

    return "title" in fields


def _preferred_layout_ids_for_modality(modality: str) -> list[str]:
    """
    These are modality-specific preferences *within* the chosen family.
    This is the missing layer that prevents a family from collapsing to the
    first vaguely compatible layout.
    """
    return {
        "title_slide": [
            "title_slide",
            "cover_image_1",
            "cover_image_2",
            "cover_image_7",
            "cover_image_8",
        ],
        "index_slide": [
            "index_slide",
        ],
        "closing_slide": [
            "thank_you",
            "title_slide",
        ],
        "context_statement": [
            "big_text",
            "fact_number",
            "title_text",
        ],
        "problem_framing": [
            "title_text",
            "title_text_two_columns",
            "title_text_split_background",
        ],
        "hypothesis_success_criteria": [
            "title_text_two_columns",
            "title_text_four_columns",
            "title_text_two_columns_diff",
        ],
        "options_considered": [
            "insight_text_boxes",
            "title_text_four_columns",
            "title_text_two_columns",
            "boxes_3_med_2_small",
            "boxes_1_large_4_small",
        ],
        "chosen_approach": [
            "title_text",
            "title_text_two_columns",
        ],
        "architecture_view": [
            "title_text_half_image",
            "title_image",
            "title_text_quarter_content_three_quarters",
            "big_text",
        ],
        "evidence_results": [
            "title_text_half_image",
            "fact_number_half_image",
            "fact_number",
            "title_text",
        ],
        "learnings_constraints": [
            "title_text",
            "title_text_two_columns",
        ],
        "implications": [
            "title_text",
            "big_text",
        ],
        "next_steps": [
            "insight_text_boxes",
            "title_text_four_columns",
            "title_text_two_columns",
            "boxes_4_tall",
        ],
        "case_study": [
            "case_study_1",
            "case_study_2",
        ],
        "strategy": [
            "title_text_four_columns",
            "title_text",
            "table",
        ],
        "prioritisation": [
            "table",
        ],
        "operating_model": [
            "table",
            "title_text_four_columns",
            "title_text",
        ],
        "section_divider": [
            "divider_standard",
            "divider_with_contents",
        ],
        "key_metric": [
            "fact_number",
            "fact_number_half_image",
            "title_text",
        ],
        "four_pillars": [
            "title_text_four_columns",
            "insight_text_boxes",
            "title_text",
        ],
        "quote_slide": [
            "quote_layout",
            "big_text",
        ],
        "ibm_sign_off": [
            "ibm_sign_off_blue80",
            "ibm_sign_off_blue60",
            "ibm_sign_off_black",
        ],
    }.get(modality, [])


def resolve_layout(
    modality: str,
    fields: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    family_name = resolve_visual_family(modality, registry)
    family_layouts = get_family_layouts(family_name, registry)

    if not family_layouts:
        raise ValueError(
            f"No candidate layouts available for modality '{modality}' in family '{family_name}'."
        )

    by_id = {layout["id"]: layout for layout in family_layouts}
    preferred_ids = _preferred_layout_ids_for_modality(modality)

    # First pass: modality-specific preferences within the chosen family
    for layout_id in preferred_ids:
        layout = by_id.get(layout_id)
        if layout and _layout_matches_fields(layout_id, fields):
            return {
                "family": family_name,
                "layout_id": layout["id"],
                "ppt_layout": layout["ppt_layout"],
                "automation_status": layout["automation_status"],
            }

    # Second pass: any matching layout in the chosen family
    for layout in family_layouts:
        if _layout_matches_fields(layout["id"], fields):
            return {
                "family": family_name,
                "layout_id": layout["id"],
                "ppt_layout": layout["ppt_layout"],
                "automation_status": layout["automation_status"],
            }

    # Third pass: family fallback, but honour modality preference order first
    for layout_id in preferred_ids:
        layout = by_id.get(layout_id)
        if layout:
            return {
                "family": family_name,
                "layout_id": layout["id"],
                "ppt_layout": layout["ppt_layout"],
                "automation_status": layout["automation_status"],
            }

    first = family_layouts[0]
    return {
        "family": family_name,
        "layout_id": first["id"],
        "ppt_layout": first["ppt_layout"],
        "automation_status": first["automation_status"],
    }