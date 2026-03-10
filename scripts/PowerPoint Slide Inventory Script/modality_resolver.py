from __future__ import annotations


def modality_candidates():
    return {
        "context_statement": [
            "large_statement",
            "headline_summary",
            "fact_statement",
        ],
        "problem_framing": [
            "title_text",
            "headline_detail",
            "multi_block_analysis",
        ],
        "hypothesis_success_criteria": [
            "title_text_two_columns",
            "four_points",
            "multi_block_analysis",
        ],
        "options_considered": [
            "insight_boxes",
            "four_points",
            "multi_block_analysis",
        ],
        "chosen_approach": [
            "title_text",
            "headline_summary",
            "headline_detail",
        ],
        "architecture_view": [
            "title_text_half_image",
            "image_story",
            "two_column_image",
        ],
        "evidence_results": [
            "fact_number_half_image",
            "fact_with_image",
            "title_text",
        ],
        "learnings_constraints": [
            "title_text",
            "headline_detail",
            "multi_block_analysis",
        ],
        "implications": [
            "title_text",
            "headline_summary",
            "large_statement",
        ],
        "next_steps": [
            "insight_boxes",
            "four_points",
            "multi_block_analysis",
        ],
        "case_study": [
            "case_study",
        ],
        "strategy": [
            "strategy_pillars",
            "value_tree",
        ],
        "prioritisation": [
            "prioritisation_matrix",
            "portfolio_matrix",
        ],
        "operating_model": [
            "operating_model_framework",
            "pyramid",
            "capability_map",
        ],
    }


def _layout_matches_fields(layout_name: str, fields: dict) -> bool:
    """
    Very simple content-shape heuristic.
    """
    if layout_name == "insight_boxes":
        return "intro" in fields and "boxes" in fields

    if layout_name == "title_text_two_columns":
        return "body_left" in fields and "body_right" in fields

    if layout_name in {"title_text_half_image", "fact_number_half_image", "fact_with_image", "image_story", "two_column_image"}:
        return "image" in fields

    if layout_name == "four_points":
        return "points" in fields and isinstance(fields["points"], list) and len(fields["points"]) == 4

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