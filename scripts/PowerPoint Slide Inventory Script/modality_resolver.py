from __future__ import annotations


def modality_candidates():
    return {
        "title_slide": [
            "title_slide",
        ],
        "index_slide": [
            "index_slide",
        ],
        "closing_slide": [
            "closing_slide",
        ],
        "context_statement": [
            "large_statement",
            "fact_number",
            "title_text",
        ],
        "problem_framing": [
            "title_text",
        ],
        "hypothesis_success_criteria": [
            "title_text_two_columns",
            "title_text_four_columns",
        ],
        "options_considered": [
            "insight_boxes",
            "title_text_four_columns",
            "title_text_two_columns",
        ],
        "chosen_approach": [
            "title_text",
        ],
        "architecture_view": [
            "title_text_half_image",
        ],
        "evidence_results": [
            "fact_number_half_image",
            "fact_number",
            "title_text",
        ],
        "learnings_constraints": [
            "title_text",
        ],
        "implications": [
            "title_text",
        ],
        "next_steps": [
            "insight_boxes",
            "title_text_four_columns",
            "title_text_two_columns",
        ],
        "case_study": [
            "case_study_1",
        ],
    }


def _layout_matches_fields(layout_id: str, fields: dict) -> bool:
    if layout_id == "title_slide":
        return "title" in fields

    if layout_id == "index_slide":
        return "title" in fields and "sections" in fields

    if layout_id == "closing_slide":
        return "title" in fields or "contact" in fields

    if layout_id == "insight_boxes":
        return "intro" in fields and "boxes" in fields

    if layout_id == "title_text_two_columns":
        return "body_left" in fields and "body_right" in fields

    if layout_id == "title_text_four_columns":
        return "points" in fields and isinstance(fields["points"], list) and len(fields["points"]) == 4

    if layout_id == "title_text_half_image":
        return "body" in fields and "image" in fields

    if layout_id == "fact_number_half_image":
        return "image" in fields and (
            ("lead" in fields and "proof_points" in fields) or "body" in fields
        )

    if layout_id == "fact_number":
        return ("lead" in fields and "proof_points" in fields) or "body" in fields

    if layout_id == "case_study_1":
        return "body_left" in fields and "body_right" in fields and "image" in fields

    if layout_id in {"large_statement", "title_text"}:
        return "title" in fields

    return True


def resolve_layout(modality: str, fields: dict, registry: dict) -> str:
    candidates = modality_candidates().get(modality)

    if not candidates:
        raise ValueError(f"No layout candidates defined for modality '{modality}'")

    available_layouts = registry["layouts"]

    for candidate in candidates:
        if candidate not in available_layouts:
            continue
        if _layout_matches_fields(candidate, fields):
            return candidate

    for candidate in candidates:
        if candidate in available_layouts:
            return candidate

    raise ValueError(
        f"No available layouts found in registry for modality '{modality}'"
    )