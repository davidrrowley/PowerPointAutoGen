from __future__ import annotations

from typing import Any

from visual_family_resolver import get_family_layouts, resolve_visual_family


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


def _layout_matches_fields(layout_id: str, fields: dict[str, Any]) -> bool:
    if layout_id in {"title_slide", "cover_image_1", "cover_image_2", "cover_image_7", "cover_image_8"}:
        return _matches_title_slide(fields)

    if layout_id == "index_slide":
        return _matches_index_slide(fields)

    if layout_id == "thank_you":
        return _matches_closing_slide(fields)

    if layout_id == "big_text":
        return "title" in fields

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
        return "body" in fields or "table_rows" in fields

    return "title" in fields


def resolve_layout(
    modality: str,
    fields: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    family_name = resolve_visual_family(modality, registry)
    family_layouts = get_family_layouts(family_name, registry)

    for layout in family_layouts:
        if _layout_matches_fields(layout["id"], fields):
            return {
                "family": family_name,
                "layout_id": layout["id"],
                "ppt_layout": layout["ppt_layout"],
                "automation_status": layout["automation_status"],
            }

    if family_layouts:
        first = family_layouts[0]
        return {
            "family": family_name,
            "layout_id": first["id"],
            "ppt_layout": first["ppt_layout"],
            "automation_status": first["automation_status"],
        }

    raise ValueError(
        f"No candidate layouts available for modality '{modality}' in family '{family_name}'."
    )