from __future__ import annotations

from typing import Any


MAX_TITLE_WORDS = 14
MAX_BULLETS = 5
MAX_INDEX_BULLETS = 14
MAX_BULLET_CHARS = 120
MAX_PARAGRAPH_CHARS = 280


def _word_count(text: str) -> int:
    return len(text.split())


def _validate_title(title: str, slide_num: int) -> None:
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"Slide {slide_num}: title must be a non-empty string.")

    if _word_count(title) > MAX_TITLE_WORDS:
        raise ValueError(
            f"Slide {slide_num}: title exceeds {MAX_TITLE_WORDS} words. "
            f"Current title: '{title}'"
        )


def _validate_bullets(
    bullets: list[str],
    slide_num: int,
    field_name: str,
    max_bullets: int = MAX_BULLETS,
) -> None:
    if not isinstance(bullets, list):
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' must be a list of bullet strings."
        )

    if len(bullets) > max_bullets:
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' has {len(bullets)} bullets, "
            f"which exceeds the limit of {max_bullets}."
        )

    for bullet in bullets:
        if not isinstance(bullet, str) or not bullet.strip():
            raise ValueError(
                f"Slide {slide_num}: field '{field_name}' contains an empty or invalid bullet."
            )
        if len(bullet) > MAX_BULLET_CHARS:
            raise ValueError(
                f"Slide {slide_num}: a bullet in '{field_name}' exceeds "
                f"{MAX_BULLET_CHARS} characters. Bullet: '{bullet}'"
            )


def _validate_paragraph(text: str, slide_num: int, field_name: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' must be a non-empty string."
        )

    if len(text) > MAX_PARAGRAPH_CHARS:
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' exceeds "
            f"{MAX_PARAGRAPH_CHARS} characters."
        )


def validate_text_constraints(deck_spec: dict[str, Any]) -> None:
    slides = deck_spec["slides"]

    for i, slide in enumerate(slides, start=1):
        fields = slide["fields"]
        modality = slide["modality"]

        if "title" in fields:
            _validate_title(fields["title"], i)

        if modality == "title_slide":
            if "subtitle" in fields:
                _validate_paragraph(str(fields["subtitle"]), i, "subtitle")

        elif modality == "index_slide":
            _validate_bullets(
                fields["sections"],
                i,
                "sections",
                max_bullets=MAX_INDEX_BULLETS,
            )

        elif modality == "closing_slide":
            if "contact" in fields:
                _validate_paragraph(str(fields["contact"]), i, "contact")

        elif modality in {
            "problem_framing",
            "chosen_approach",
            "architecture_view",
            "learnings_constraints",
            "implications",
            "strategy",
            "prioritisation",
            "operating_model",
        }:
            body = fields["body"]
            if isinstance(body, list):
                _validate_bullets(body, i, "body")
            else:
                _validate_paragraph(str(body), i, "body")

        elif modality == "evidence_results":
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body")
                else:
                    _validate_paragraph(str(body), i, "body")
            else:
                _validate_paragraph(str(fields["lead"]), i, "lead")
                _validate_bullets(fields["proof_points"], i, "proof_points")

        elif modality == "options_considered":
            if "body_left" in fields and "body_right" in fields:
                left = fields["body_left"]
                right = fields["body_right"]

                if isinstance(left, list):
                    _validate_bullets(left, i, "body_left")
                else:
                    _validate_paragraph(str(left), i, "body_left")

                if isinstance(right, list):
                    _validate_bullets(right, i, "body_right")
                else:
                    _validate_paragraph(str(right), i, "body_right")

            elif "intro" in fields and "boxes" in fields:
                intro = fields["intro"]
                boxes = fields["boxes"]

                if isinstance(intro, list):
                    _validate_bullets(intro, i, "intro")
                else:
                    _validate_paragraph(str(intro), i, "intro")

                _validate_bullets(boxes, i, "boxes")

            elif "points" in fields:
                _validate_bullets(fields["points"], i, "points")

        elif modality in {
            "hypothesis_success_criteria",
            "next_steps",
            "case_study",
        }:
            left = fields["body_left"]
            right = fields["body_right"]

            if isinstance(left, list):
                _validate_bullets(left, i, "body_left")
            else:
                _validate_paragraph(str(left), i, "body_left")

            if isinstance(right, list):
                _validate_bullets(right, i, "body_right")
            else:
                _validate_paragraph(str(right), i, "body_right")

        elif modality == "key_metric":
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body")
                else:
                    _validate_paragraph(str(body), i, "body")

        elif modality == "four_pillars":
            columns = fields.get("columns", [])
            _validate_bullets(columns, i, "columns", max_bullets=4)

        elif modality == "quote_slide":
            _validate_paragraph(str(fields["quote"]), i, "quote")
            if "attribution" in fields:
                _validate_paragraph(str(fields["attribution"]), i, "attribution")

        # section_divider and ibm_sign_off have only title / no text — already validated above