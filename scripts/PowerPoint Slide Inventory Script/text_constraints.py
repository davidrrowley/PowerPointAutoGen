from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Global fallback limits (used when no per-modality override exists)
# ---------------------------------------------------------------------------
MAX_TITLE_WORDS = 14
MAX_BULLETS = 5
MAX_INDEX_BULLETS = 14
MAX_BULLET_CHARS = 120
MAX_PARAGRAPH_CHARS = 280

# ---------------------------------------------------------------------------
# Per-modality constraints — derived from IBM template placeholder dimensions
# (ibm_template_inventory.json).  Each entry overrides the globals above for
# that modality.  Fields not listed fall back to the globals.
#
# Key layout facts:
#   Wide single-column  ("title, text")           : 4.51" × 4.70"  ~130 ch/line ~16 lines
#   Wide two-column     ("title, text (two cols)"): 4.51" × 3.56" each ~130 ch/line ~12 lines
#   Narrow four-column  ("title, text (4 cols)")  : 2.01" × 3.56" each  ~58 ch/line ~12 lines
#   Narrow case-study   ("case study 1 ...")      : 2.01" × 3.56" each  ~58 ch/line ~12 lines
#   Index/sections      ("title, text")           : 4.51" wide but items are short labels
# ---------------------------------------------------------------------------
MODALITY_CONSTRAINTS: dict[str, dict] = {
    # --- Narrow-column layouts (2.01" per column) ----------------------------
    # four_pillars → "title, text (four columns)" : 4 × 2.01" narrow
    "four_pillars": {
        "max_bullets": 5,          # per column; physical max ~12, exec readability = 5
        "max_bullet_chars": 90,    # body lines wrap across the 2.01" column; 90 chars is safe
    },
    # case_study → "case study 1: title, text (two columns), half-image" : 2 × 2.01" narrow
    "case_study": {
        "max_bullets": 8,          # case studies benefit from more detail
        "max_bullet_chars": 90,
    },

    # --- Wide single-column layouts (4.51" × 4.70") --------------------------
    # Template has room for 16 lines; executive readability cap raised slightly
    "context_statement":       {"max_bullets": 7, "max_bullet_chars": 120},
    "problem_framing":         {"max_bullets": 7, "max_bullet_chars": 120},
    "chosen_approach":         {"max_bullets": 7, "max_bullet_chars": 120},
    "architecture_view":       {"max_bullets": 7, "max_bullet_chars": 120},
    "learnings_constraints":   {"max_bullets": 7, "max_bullet_chars": 120},
    "implications":            {"max_bullets": 7, "max_bullet_chars": 120},
    "strategy":                {"max_bullets": 7, "max_bullet_chars": 120},
    "prioritisation":          {"max_bullets": 7, "max_bullet_chars": 120},
    "operating_model":         {"max_bullets": 7, "max_bullet_chars": 120},
    "evidence_results":        {"max_bullets": 7, "max_bullet_chars": 120},
    "key_metric":              {"max_bullets": 5, "max_bullet_chars": 120},

    # --- Wide two-column layouts (4.51" per column, 3.56" tall) --------------
    # Each side has a full-width 4.51" column so 120 chars/line is fine.
    # Physical limit ~12 lines; exec readability cap = 8 per side.
    "hypothesis_success_criteria": {"max_bullets": 8, "max_bullet_chars": 120},
    "options_considered":          {"max_bullets": 8, "max_bullet_chars": 120},
    "next_steps":                  {"max_bullets": 8, "max_bullet_chars": 120},

    # --- Index / agenda slide -----------------------------------------------
    # Sections are short labels, not full sentences.
    "index_slide": {
        "max_bullets": MAX_INDEX_BULLETS,   # up to 14
        "max_bullet_chars": 80,
    },
}


def get_constraints(modality: str) -> dict:
    """Return the effective constraints for a given modality.

    Starts from the global defaults and applies any per-modality overrides.
    Always returns a complete dict with all four keys.
    """
    base = {
        "max_bullets":        MAX_BULLETS,
        "max_bullet_chars":   MAX_BULLET_CHARS,
        "max_paragraph_chars": MAX_PARAGRAPH_CHARS,
        "max_title_words":    MAX_TITLE_WORDS,
    }
    base.update(MODALITY_CONSTRAINTS.get(modality, {}))
    return base


def _word_count(text: str) -> int:
    return len(text.split())


def _validate_title(title: str, slide_num: int, max_words: int = MAX_TITLE_WORDS) -> None:
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"Slide {slide_num}: title must be a non-empty string.")

    if _word_count(title) > max_words:
        raise ValueError(
            f"Slide {slide_num}: title exceeds {max_words} words. "
            f"Current title: '{title}'"
        )


def _validate_bullets(
    bullets: list[str],
    slide_num: int,
    field_name: str,
    max_bullets: int = MAX_BULLETS,
    max_bullet_chars: int = MAX_BULLET_CHARS,
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
        if len(bullet) > max_bullet_chars:
            raise ValueError(
                f"Slide {slide_num}: a bullet in '{field_name}' exceeds "
                f"{max_bullet_chars} characters. Bullet: '{bullet}'"
            )


def _validate_paragraph(
    text: str,
    slide_num: int,
    field_name: str,
    max_chars: int = MAX_PARAGRAPH_CHARS,
) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' must be a non-empty string."
        )

    if len(text) > max_chars:
        raise ValueError(
            f"Slide {slide_num}: field '{field_name}' exceeds "
            f"{max_chars} characters."
        )


def validate_text_constraints(deck_spec: dict[str, Any]) -> None:
    slides = deck_spec["slides"]

    for i, slide in enumerate(slides, start=1):
        fields = slide["fields"]
        modality = slide["modality"]

        # Resolve per-modality limits once per slide
        c = get_constraints(modality)
        mb   = c["max_bullets"]
        mbc  = c["max_bullet_chars"]
        mpc  = c["max_paragraph_chars"]
        mtw  = c["max_title_words"]

        if "title" in fields:
            _validate_title(fields["title"], i, max_words=mtw)

        if modality == "title_slide":
            if "subtitle" in fields:
                _validate_paragraph(str(fields["subtitle"]), i, "subtitle", max_chars=mpc)

        elif modality == "index_slide":
            _validate_bullets(
                fields["sections"],
                i,
                "sections",
                max_bullets=mb,
                max_bullet_chars=mbc,
            )

        elif modality == "closing_slide":
            if "contact" in fields:
                _validate_paragraph(str(fields["contact"]), i, "contact", max_chars=mpc)

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
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(body), i, "body", max_chars=mpc)
            elif "body_left" in fields or "body_right" in fields:
                for side in ("body_left", "body_right"):
                    if side in fields:
                        val = fields[side]
                        if isinstance(val, list):
                            _validate_bullets(val, i, side, max_bullets=mb, max_bullet_chars=mbc)
                        else:
                            _validate_paragraph(str(val), i, side, max_chars=mpc)
            elif "points" in fields:
                _validate_bullets(fields["points"], i, "points", max_bullets=mb, max_bullet_chars=mbc)
            elif "columns" in fields:
                _validate_bullets(fields["columns"], i, "columns", max_bullets=4, max_bullet_chars=mbc)

        elif modality == "evidence_results":
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(body), i, "body", max_chars=mpc)
            else:
                _validate_paragraph(str(fields["lead"]), i, "lead", max_chars=mpc)
                _validate_bullets(fields["proof_points"], i, "proof_points", max_bullets=mb, max_bullet_chars=mbc)

        elif modality == "options_considered":
            if "body_left" in fields and "body_right" in fields:
                left = fields["body_left"]
                right = fields["body_right"]

                if isinstance(left, list):
                    _validate_bullets(left, i, "body_left", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(left), i, "body_left", max_chars=mpc)

                if isinstance(right, list):
                    _validate_bullets(right, i, "body_right", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(right), i, "body_right", max_chars=mpc)

            elif "intro" in fields and "boxes" in fields:
                intro = fields["intro"]
                boxes = fields["boxes"]

                if isinstance(intro, list):
                    _validate_bullets(intro, i, "intro", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(intro), i, "intro", max_chars=mpc)

                _validate_bullets(boxes, i, "boxes", max_bullets=mb, max_bullet_chars=mbc)

            elif "points" in fields:
                _validate_bullets(fields["points"], i, "points", max_bullets=mb, max_bullet_chars=mbc)

        elif modality in {
            "hypothesis_success_criteria",
            "next_steps",
            "case_study",
        }:
            for side in ("body_left", "body_right"):
                if side in fields:
                    val = fields[side]
                    if isinstance(val, list):
                        _validate_bullets(val, i, side, max_bullets=mb, max_bullet_chars=mbc)
                    else:
                        _validate_paragraph(str(val), i, side, max_chars=mpc)

        elif modality == "key_metric":
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(body), i, "body", max_chars=mpc)

        elif modality == "four_pillars":
            pillars = fields.get("pillars", fields.get("columns", []))
            if isinstance(pillars, list):
                if len(pillars) > 4:
                    raise ValueError(
                        f"Slide {i}: four_pillars must have exactly 4 pillars, got {len(pillars)}."
                    )
                for pi, pillar in enumerate(pillars, start=1):
                    if isinstance(pillar, dict):
                        body = pillar.get("body", "")
                        if isinstance(body, list):
                            _validate_bullets(body, i, f"pillars[{pi}].body", max_bullets=mb, max_bullet_chars=mbc)
                        elif body:
                            _validate_paragraph(str(body), i, f"pillars[{pi}].body", max_chars=mbc)

        elif modality == "quote_slide":
            _validate_paragraph(str(fields["quote"]), i, "quote", max_chars=mpc)
            if "attribution" in fields:
                _validate_paragraph(str(fields["attribution"]), i, "attribution", max_chars=mpc)

        elif modality == "context_statement":
            if "body" in fields:
                body = fields["body"]
                if isinstance(body, list):
                    _validate_bullets(body, i, "body", max_bullets=mb, max_bullet_chars=mbc)
                else:
                    _validate_paragraph(str(body), i, "body", max_chars=mpc)

        # section_divider and ibm_sign_off have only title / no text — already validated above
