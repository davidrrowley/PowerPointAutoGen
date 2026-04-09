# Slide Generation Quality Framework

## Context

This project generates IBM Consulting PowerPoint slides from a YAML deck spec, rendered against
`IBM_Consulting_Presentation_Template_2022_V02_Arial.potx` using `render_from_yaml.py`.

The automated refinement pipeline (`refine_deck.py`) runs up to 3 iterations of:
1. **Render** — YAML → PPTX via `render_from_yaml.py`
2. **Preview** — PPTX → PNG via `render_slide_previews.py` (PowerPoint COM)
3. **Critique** — PNGs sent to `gpt-4.1` vision model via `critique_slides.py`
4. **Rewrite** — low-scoring slides rewritten by `gpt-5.4-nano` text model in `refine_deck.py`

The objective is slides that are:
- Structurally valid (schema + text constraints pass deterministic validation)
- Visually balanced (no large blank regions, no overflow, appropriate layout for content)
- Consistent with IBM brand (IBM Blue accents, Arial/IBM Plex Sans, white/light-grey backgrounds)
- Appropriate for executive-level communication

---

## Core Principle

Slide quality is multi-dimensional. Repairs must be targeted, not full regenerations.

Prefer changing a **field value** before changing a **modality**.
Only change modality when content fundamentally doesn't fit the current layout.

---

## Modalities (Real Archetypes)

Every slide in the YAML deck must have a `modality:` field set to one of the following.
Mapping to the old archetype vocabulary is shown for reference.

| Modality | Archetype equivalent | Typical use |
|---|---|---|
| `title_slide` | TITLE | Cover / deck opener |
| `index_slide` | SUMMARY | Agenda / table of contents (up to 14 sections) |
| `section_divider` | SECTION_DIVIDER | IBM Blue branded transition slide |
| `closing_slide` | TITLE | End of deck, call to action |
| `ibm_sign_off` | TITLE | IBM legal / branding sign-off page |
| `context_statement` | EXEC_MESSAGE | Single strong statement; body optional |
| `problem_framing` | EXEC_MESSAGE | Problem definition; body or body_left/body_right |
| `hypothesis_success_criteria` | EXEC_MESSAGE | Hypothesis + criteria; body or two-column |
| `chosen_approach` | PROCESS | Recommended path; body or two-column |
| `options_considered` | COMPARISON | 3 variants: two-column, intro+boxes, or points list |
| `architecture_view` | ARCHITECTURE | System/solution diagram context; body or two-column |
| `evidence_results` | EVIDENCE | Data / proof; body list OR lead + proof_points |
| `learnings_constraints` | SUMMARY | Key findings; body or two-column |
| `implications` | EXEC_MESSAGE | So-what; body or two-column |
| `next_steps` | TIMELINE | Actions; body or two-column |
| `case_study` | EVIDENCE | Always two-column + image |
| `strategy` | PROCESS | Strategic direction; body or two-column |
| `prioritisation` | PROCESS | Ranked items; body or two-column |
| `operating_model` | ARCHITECTURE | Org/ops structure; body or two-column |
| `four_pillars` | PROCESS | Exactly 4 pillar objects, each with title + body |
| `key_metric` | EVIDENCE | Single headline number; metric + supporting_text |
| `quote_slide` | EXEC_MESSAGE | Attribution quote |

### Modality selection rules

- **4 parallel items of equal weight** → `four_pillars` (exactly 4 required)
- **2 options being compared** → `options_considered` with `body_left`/`body_right`
- **3–5 options with short descriptions** → `options_considered` with `intro` + `boxes`
- **Single strong statement / exec narrative** → `context_statement` or `implications`
- **Recommended path after options** → `chosen_approach`
- **Data point with supporting evidence** → `evidence_results` with `lead` + `proof_points`
- **Agenda** → `index_slide` (sections list, up to 14)
- **IBM Blue branded transition** → `section_divider`
- **Timeline / ordered actions** → `next_steps`

If classification is unclear, infer from content intent. Do NOT default to `problem_framing` as a
catch-all.

---

## Content Budgeting (Pre-Layout Gate)

These are **enforced programmatically** by `text_constraints.py` (`get_constraints(modality)`) and
will raise `ValueError` if violated. Limits are derived from the IBM template placeholder dimensions
in `ibm_template_inventory.json` — narrow columns get tighter limits.

| Modality group | Max bullets (per column/field) | Max chars per bullet | Enforced by |
|---|---|---|---|
| Title field (all slides) | — | — ≤14 words | `MAX_TITLE_WORDS` |
| Paragraph fields (`quote`, `contact`, `subtitle`, `lead`) | — | ≤280 chars | `MAX_PARAGRAPH_CHARS` |
| `four_pillars` | 5 per column | **60** (narrow 2.01" col) | `MODALITY_CONSTRAINTS` |
| `case_study` | 8 per side | **60** (narrow 2.01" col) | `MODALITY_CONSTRAINTS` |
| `index_slide` sections | 14 | 80 | `MODALITY_CONSTRAINTS` |
| `options_considered`, `next_steps`, `hypothesis_success_criteria` | 8 per side | 120 | `MODALITY_CONSTRAINTS` |
| `key_metric` | 5 | 120 | `MODALITY_CONSTRAINTS` |
| All other content slides | 7 | 120 | `MODALITY_CONSTRAINTS` |
| Global fallback (unknown modality) | 5 | 120 | `MAX_BULLETS`, `MAX_BULLET_CHARS` |

### Post-LLM sanitisation (`_sanitize_slide_fields` in `refine_deck.py`)

Before validation, the rewrite pipeline automatically:
1. Strips null/empty list items
2. Truncates any bullet exceeding `get_constraints(modality)["max_bullet_chars"]`
3. If a list field exceeds its `max_bullets` limit (e.g. `boxes: [10 items]` on a 7-bullet slide):
   - Splits into `body_left` / `body_right` at the midpoint (preferred)
   - If current modality doesn't support two-column, promotes to `options_considered`
   - If list exceeds `two_col_max × 2`, fills both columns to `two_col_max` each (currently 8+8)

The LLM should target the per-modality bullet limit above; single-column overflow up to 16 is recoverable via two-column promotion.

---

## Quality Scorecard (Vision Model)

`critique_slides.py` sends PNGs to a vision model and returns per-slide JSON:

```json
{
  "slide_number": 7,
  "layout_assessment": "needs_improvement",
  "issues": ["Large blank area bottom-right", "Title too long"],
  "suggestions": ["Move to two-column layout", "Shorten title to 8 words"],
  "overall_score": 4
}
```

Scores are **1–10** (not 0–100). A slide is considered passing at **≥ 7/10**.

The vision model evaluates against these IBM Consulting standards:
- **Brand compliance**: IBM Blue (`#0043CE`) on dividers/accents, white/light-grey backgrounds, Arial/IBM Plex Sans
- **Layout fit**: Is the modality the right choice for this content? (e.g. 4 parallel items should use `four_pillars`)
- **Whitespace**: No large blank regions
- **Text density**: ≤ 5 bullets, ≤ 120 chars each, ≤ 14-word title
- **Overflow**: Text must not overflow its placeholder

### Recommended: extend critique dimensions

The current critique prompt covers visual quality but not:
- **Narrative flow**: Does this slide logically follow the previous one?
- **IBM archetype fit**: Is the modality the best choice given the content structure?
- **Specificity**: Are bullets concrete and evidence-based, or generic filler?

Consider adding a second critique pass with a text-only model that receives the full YAML deck and
evaluates cross-slide coherence. This could produce a deck-level score alongside the per-slide score.

---

## Deterministic Validation (Non-LLM Checks)

Implemented and enforced before render:

| Check | Implementation |
|---|---|
| Modality exists in registry | `schema_validation.validate_deck_structure` |
| Required fields present | `schema_validation.REQUIRED_FIELDS_BY_MODALITY` |
| `options_considered` variant consistency | `schema_validation.validate_deck_structure` |
| `evidence_results` variant consistency | `schema_validation.validate_deck_structure` |
| Title word count | `text_constraints.validate_text_constraints` |
| Bullet count per field | `text_constraints.validate_text_constraints` |
| Bullet character length | `text_constraints.validate_text_constraints` |
| Paragraph character length | `text_constraints.validate_text_constraints` |

**Now also implemented**:
- Duplicate slide title detection (warning on stderr)
- `four_pillars` `pillars` or `columns` must have exactly 4 items (hard error)
- `case_study` `image` field checked against filesystem when `base_dir` is supplied (warning)
- Cross-slide: `index_slide.sections` count vs `section_divider` count (warning)

---

## Repair Strategy

### Rewrite loop (`refine_deck.py`)

Only slides scoring **< score_threshold** (default 7) are rewritten each iteration.
The rewrite model receives: current YAML + score + issues + suggestions.

Retry logic:
1. **YAML parse failure** → retry once at `temperature=0.1` with explicit "YAML only" instruction; logs raw response on both failures
2. **Missing required fields** → retry up to 2× with field names injected into the prompt
3. **List overflow** → handled by `_sanitize_slide_fields` post-parse (no LLM retry needed)

Principle:
- Fix only identified violations
- Preserve title and modality unless the critique explicitly says to change them
- Do NOT regenerate slides that scored ≥ threshold

### Escalation

If a slide fails to improve after 3 full pipeline iterations, the final YAML keeps the best
version seen. There is currently no automatic modality-change escalation; that is done by the
sanitiser only when hard content limits are hit.

**Implemented**: slides stuck below threshold for 2+ consecutive iterations are re-prompted
with an explicit instruction to consider an alternative modality (`escalate_modality=True`
in `rewrite_slide_with_llm`). The stuck counter is tracked in `slides_stuck` and resets when
a slide passes.

---

## Iteration Control

| Setting | Default | CLI flag |
|---|---|---|
| Max iterations | 3 | `--iterations N` |
| Score threshold (rewrite trigger) | 7 | `--score-threshold N` |
| Rewrite model | `gpt-5.4-nano` | `--rewrite-model MODEL` |
| Critique/vision model | `gpt-4.1` | `--model MODEL` |

The pipeline stops after `--iterations` regardless of score. There is currently no early-exit
if all slides reach threshold.

**Recommended**: add `--early-stop` flag — exit when all slides score ≥ threshold to save LLM calls.

---

## Diagram / Architecture Slides

`architecture_view` slides currently render text content only (body or two-column bullets).
True node-edge diagrams are not yet supported by the pipeline.

If an architecture slide needs a visual diagram:
- Use `body_left`/`body_right` to describe components in two columns
- Use `four_pillars` if there are exactly 4 architectural layers/zones
- A future enhancement could generate a Mermaid/PlantUML diagram and embed as an image placeholder

---

## Typography Rules

Enforced via `text_constraints.py` + IBM template placeholder sizes:
- Titles: Arial Bold, single size within the template placeholder
- Body: Arial Regular, consistent size — do NOT mix font sizes within a field
- Max bullet length: 120 characters — favour concise, scan-able text
- Paragraphs (non-list body): max 280 characters — favour short impactful statements

---

## Final Acceptance Criteria

A slide is considered complete when:
- `overall_score` ≥ 7/10 from vision critique
- `layout_assessment` = `good` or `acceptable`
- No `ValueError` from `validate_deck_structure` or `validate_text_constraints`
- No WARNING lines in `refined/refinement.log` for that slide number

A deck is considered complete when all slides meet the above, or 3 iterations have been exhausted.
