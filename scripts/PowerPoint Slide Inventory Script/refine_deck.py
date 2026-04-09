"""
refine_deck.py
--------------
Automated refinement loop for IBM Consulting deck generation.

Pipeline (repeated --iterations times):

    1. render_from_yaml.py   → generates .pptx from YAML
    2. render_slide_previews → exports slide PNGs via PowerPoint COM
    3. critique_slides.py    → vision model scores each slide
    4. LLM rewriter          → reads critique + current YAML, rewrites low-scoring slides

After all iterations the final .pptx and YAML are written to --output-dir.

Usage:
    python refine_deck.py \\
        --deck ibm_stable_nrw.yaml \\
        --template IBM_Consulting_Presentation_Template_2022_V02_Arial.potx \\
        --output-dir refined/ \\
        [--iterations 3] \\
        [--model gpt-4o] \\
        [--score-threshold 7]

Environment (provider auto-detected from env vars):
    OPENAI_API_KEY  -> OpenAI API (recommended, no daily rate limit)
    GITHUB_TOKEN    -> GitHub Models (50 req/day free tier)
    If both are set, OPENAI_API_KEY takes priority.
    Override with --provider github|openai.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise RuntimeError("PyYAML is required. Install with: pip install pyyaml") from exc

# ---------------------------------------------------------------------------
# Logging: tee stdout/stderr to a file
# ---------------------------------------------------------------------------


class _Tee(io.TextIOBase):
    """Write to both a wrapped stream and a log file simultaneously."""

    def __init__(self, stream, log_path: Path):
        self._stream = stream
        self._log = open(log_path, "a", encoding="utf-8")

    def write(self, data):
        self._stream.write(data)
        self._stream.flush()
        self._log.write(data)
        self._log.flush()
        return len(data)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def close(self):
        self._log.close()


def _setup_logging(log_path: Path) -> tuple[_Tee, _Tee]:
    """Redirect stdout and stderr through a Tee so everything is logged."""
    tee_out = _Tee(sys.__stdout__, log_path)
    tee_err = _Tee(sys.__stderr__, log_path)
    sys.stdout = tee_out
    sys.stderr = tee_err
    return tee_out, tee_err

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"

_REWRITE_SYSTEM_PROMPT = """\
You are an expert IBM Consulting presentation designer and copywriter.
You will be given:
  1. The current YAML specification for a single presentation slide.
  2. A critique of that slide from a vision model, including issues, suggestions, and a score.

Your job is to rewrite the YAML slide spec to fix the identified issues while:
- Keeping the same core message and factual content
- Choosing the most appropriate modality for the content type
- Following IBM Consulting presentation standards (IBM Blue accents, Arial font, ≤14-word title)
- Respecting per-modality bullet limits: four_pillars/case_study ≤60 chars/bullet (narrow 2" columns); options_considered/next_steps/hypothesis_success_criteria ≤8 bullets per side; most content slides ≤7 bullets ≤120 chars; key_metric ≤5 bullets
- Returning ONLY a valid YAML block for that single slide — no prose, no code fences, no extra keys
- YAML RULE: Any string value that contains ': ' (colon followed by space) MUST be wrapped in double quotes. Example: `title: "Joint proposition: scale and value"` NOT `title: Joint proposition: scale and value`

OUTPUT STRUCTURE (mandatory):
  modality: <modality_name>
  fields:
    <field_name>: <value>
    ...

Modalities and their REQUIRED fields inside `fields:`:
  title_slide       → title (+ optional subtitle)
  index_slide       → title, sections (list of strings)
  closing_slide     → (no required fields)
  context_statement → title (+ optional body list)
  problem_framing   → title (+ optional body list)
  hypothesis_success_criteria → title (+ optional body list)
  options_considered → title + either: body_left/body_right, or intro/boxes, or points
  chosen_approach   → title (+ optional body list)
  architecture_view → title (+ optional body list)
  evidence_results  → title + either: body list, or lead/proof_points
  learnings_constraints → title (+ optional body list)
  implications      → title (+ optional body list)
  next_steps        → title (+ optional body list)
  case_study        → title, body_left, body_right, image
  strategy          → title (+ optional body list)
  prioritisation    → title (+ optional body list)
  operating_model   → title (+ optional body list)
  section_divider   → title (+ optional subtitle)
  key_metric        → title (+ optional metric, supporting_text)
  four_pillars      → title, pillars (list of 4 items each with title + body)
  quote_slide       → quote (+ optional attribution)
  ibm_sign_off      → (no required fields)

Return the slide as a YAML mapping with `modality:` and `fields:` as the only top-level keys.
"""

_REWRITE_USER_PROMPT = """\
## Current slide YAML

```yaml
{slide_yaml}
```

## Critique (score {score}/10)

Layout assessment: {layout_assessment}

Issues:
{issues}

Suggestions:
{suggestions}

Rewrite this slide to address the critique. Return ONLY the improved YAML mapping.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client(provider: str = "auto"):
    """Return an OpenAI client pointed at the right backend.

    provider='auto': Azure if AZURE_OPENAI_ENDPOINT/OPENAI_BASE_URL set, else
                     OpenAI if OPENAI_API_KEY set, else GitHub Models.
    provider='azure': require OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL.
    provider='openai': require OPENAI_API_KEY.
    provider='github': require GITHUB_TOKEN.
    """
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as exc:
        raise RuntimeError("openai is required. Install with: pip install openai") from exc

    openai_key = os.environ.get("OPENAI_API_KEY")
    github_key = os.environ.get("GITHUB_TOKEN")
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("OPENAI_BASE_URL")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    # Strip project-level path — AzureOpenAI needs the resource root, e.g.
    # https://foo.services.ai.azure.com/ not .../api/projects/bar
    if azure_endpoint:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(azure_endpoint)
        # Keep only scheme + netloc (drop any path)
        azure_endpoint = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    if provider == "azure" or (provider == "auto" and openai_key and azure_endpoint):
        if not openai_key:
            print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
            sys.exit(1)
        if not azure_endpoint:
            print("ERROR: AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL is not set.", file=sys.stderr)
            sys.exit(1)
        print(f"[provider] Azure OpenAI ({azure_endpoint})")
        return AzureOpenAI(
            api_key=openai_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
        )

    if provider == "openai" or (provider == "auto" and openai_key):
        if not openai_key:
            print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
            sys.exit(1)
        print("[provider] OpenAI API")
        return OpenAI(api_key=openai_key)

    if provider == "github" or (provider == "auto" and github_key):
        if not github_key:
            print("ERROR: GITHUB_TOKEN is not set.", file=sys.stderr)
            sys.exit(1)
        print("[provider] GitHub Models (50 req/day free tier)")
        return OpenAI(base_url=_GITHUB_MODELS_BASE_URL, api_key=github_key)

    print(
        "ERROR: No LLM credentials found.\n"
        "  Set OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT (Azure AI Foundry),\n"
        "  OPENAI_API_KEY (OpenAI), or GITHUB_TOKEN (GitHub Models).",
        file=sys.stderr,
    )
    sys.exit(1)


def _run(cmd: list[str], label: str) -> bool:
    """Run a subprocess, stream output, return True on success."""
    print(f"\n>>> {label}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(f"FAILED: {result.stderr}", file=sys.stderr)
        return False
    return True


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_yaml(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _slide_to_yaml_str(slide: dict) -> str:
    return yaml.dump(slide, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _repair_unquoted_colon_values(text: str) -> str:
    """Quote YAML scalar values/list-items that contain ': ' and break the parser."""
    import re
    lines = text.splitlines()
    fixed = []
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        # Mapping value: "  key: value that: has colons"
        kv_m = re.match(r'^([\w][\w _-]*):\s+(.+)$', stripped)
        if kv_m:
            key, val = kv_m.group(1), kv_m.group(2)
            if ': ' in val and val[:1] not in ('"', "'", '[', '{', '|', '>', '!', '&', '*'):
                val = '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'
                line = indent + key + ': ' + val
        else:
            # List item: "  - value that: has colons"
            li_m = re.match(r'^(-\s+)(.+)$', stripped)
            if li_m:
                prefix, val = li_m.group(1), li_m.group(2)
                if ': ' in val and val[:1] not in ('"', "'", '[', '{', '!'):
                    # Don't quote items whose key part is a structural YAML key
                    # (e.g. "title:", "body:", "label:") — those are valid dict entries,
                    # not broken plain-text bullets like "CRM: Dynamics 365".
                    item_key = val.split(':', 1)[0]
                    if re.match(r'^[a-z][a-z_]*$', item_key):
                        pass  # structural key — leave as-is
                    else:
                        val = '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'
                        line = indent + prefix + val
        fixed.append(line)
    return '\n'.join(fixed)


def _parse_slide_yaml(raw: str) -> dict | None:
    """Parse LLM response as a YAML slide mapping, stripping code fences and <think> blocks."""
    import re
    text = raw.strip()
    # Strip <think>...</think> reasoning blocks (o-series / newer models)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                inner.append(line)
        text = "\n".join(inner)
    def _has_dict_bullets(parsed: dict) -> bool:
        """Return True if any plain-bullet list field contains single-key dict items.

        A single-key dict like {"CRM": "Dynamics 365"} means the LLM wrote
        ``- CRM: Dynamics 365`` without quoting — PyYAML silently coerces it.
        Multi-key dicts (e.g. {"title": "...", "body": "..."}) are legitimate
        structured objects (used by four_pillars pillars:, options_considered, etc.)
        and must NOT be flagged.
        """
        fields = parsed.get("fields") or {}
        for v in fields.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and len(item) == 1:
                        return True
        return False

    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict) and "modality" in parsed:
            if not _has_dict_bullets(parsed):
                return parsed
            # List items are dicts (unquoted 'key: value' bullets) — fall through to repair
    except yaml.YAMLError:
        pass

    # Attempt repair: quote values/bullets that contain ': ' and break the parser
    try:
        repaired = _repair_unquoted_colon_values(text)
        parsed = yaml.safe_load(repaired)
        if isinstance(parsed, dict) and "modality" in parsed:
            return parsed
    except yaml.YAMLError:
        pass
    return None


def _sanitize_slide_fields(slide: dict) -> dict:
    """Remove empty/null items from all list fields, and handle overflow by splitting to two-column.

    Uses per-modality constraints from text_constraints.get_constraints() so limits are
    always in sync with the validator.
    """
    from text_constraints import get_constraints, MAX_BULLETS

    modality = slide.get("modality", "")
    c = get_constraints(modality)
    mb  = c["max_bullets"]
    mbc = c["max_bullet_chars"]

    # Modalities that support body_left/body_right two-column layout
    _TWO_COL_MODALITIES = {
        "options_considered", "problem_framing", "chosen_approach",
        "architecture_view", "learnings_constraints", "implications",
        "strategy", "prioritisation", "operating_model",
        "hypothesis_success_criteria", "next_steps",
    }

    # Fields with their own hard column limits (not bullet-count but column count)
    _COLUMN_MAX = {"pillars": 4, "columns": 4, "sections": c["max_bullets"]}

    fields = slide.get("fields")
    if not isinstance(fields, dict):
        return slide

    cleaned = {}
    overflowed_field = None   # (field_name, items) if we need to split

    for key, val in fields.items():
        if isinstance(val, list):
            # Filter empty/null items and truncate over-length bullets
            items = [
                (item if isinstance(item, str) else str(item))[:mbc]
                for item in val
                if item is not None and str(item).strip()
            ]
            limit = _COLUMN_MAX.get(key, mb)
            if len(items) > limit and key in ("body", "boxes", "points", "proof_points"):
                # Candidate for two-column promotion instead of truncation
                overflowed_field = (key, items)
                cleaned[key] = items  # keep for now; may be replaced below
            else:
                if len(items) > limit:
                    print(
                        f"    [sanitize] field '{key}' had {len(items)} items — truncated to {limit}.",
                        file=sys.stderr,
                    )
                    items = items[:limit]
                cleaned[key] = items
        else:
            cleaned[key] = val

    # Promote to two-column if a single-column field overflowed and modality supports it
    two_col_max = get_constraints("options_considered")["max_bullets"]  # wide two-col limit
    if overflowed_field:
        field_name, items = overflowed_field
        if modality in _TWO_COL_MODALITIES and len(items) <= two_col_max * 2:
            mid = (len(items) + 1) // 2
            left, right = items[:mid], items[mid:]
            print(
                f"    [sanitize] '{field_name}' had {len(items)} items — split to "
                f"body_left ({len(left)}) / body_right ({len(right)}) on '{modality}'.",
                file=sys.stderr,
            )
            cleaned.pop(field_name, None)
            cleaned.pop("boxes", None)
            cleaned["body_left"] = left
            cleaned["body_right"] = right
        elif modality not in _TWO_COL_MODALITIES:
            # Fallback: promote modality to options_considered and split
            mid = (len(items) + 1) // 2
            left, right = items[:mid], items[mid:]
            print(
                f"    [sanitize] '{field_name}' overflowed on '{modality}' (no two-col support) — "
                f"converting to options_considered with body_left/body_right.",
                file=sys.stderr,
            )
            cleaned.pop(field_name, None)
            cleaned["body_left"] = left
            cleaned["body_right"] = right
            return {"modality": "options_considered", "fields": cleaned}
        else:
            # More than two_col_max*2 items — truncate to two full columns
            left, right = items[:two_col_max], items[two_col_max:two_col_max * 2]
            print(
                f"    [sanitize] '{field_name}' had {len(items)} items (>{two_col_max*2}) — "
                f"split to body_left ({len(left)}) / body_right ({len(right)}) and truncated.",
                file=sys.stderr,
            )
            cleaned.pop(field_name, None)
            cleaned.pop("boxes", None)
            cleaned["body_left"] = left
            cleaned["body_right"] = right

    return {**slide, "fields": cleaned}


# ---------------------------------------------------------------------------
# Core rewrite step
# ---------------------------------------------------------------------------


def rewrite_slide_with_llm(
    client,
    model: str,
    slide: dict,
    critique_record: dict,
    escalate_modality: bool = False,
) -> dict:
    """Ask the LLM to rewrite a single slide based on its critique. Returns the improved slide dict."""
    issues_text = "\n".join(f"  - {i}" for i in critique_record.get("issues", []))
    suggestions_text = "\n".join(f"  - {s}" for s in critique_record.get("suggestions", []))

    user_msg = _REWRITE_USER_PROMPT.format(
        slide_yaml=_slide_to_yaml_str(slide),
        score=critique_record.get("overall_score", "?"),
        layout_assessment=critique_record.get("layout_assessment", "?"),
        issues=issues_text or "  (none)",
        suggestions=suggestions_text or "  (none)",
    )

    if escalate_modality:
        user_msg += (
            "\n\nESCALATION: This slide has scored below the threshold for 2 or more consecutive "
            "iterations. The current modality may be the wrong choice for this content. "
            "Consider whether a different modality would better suit the content structure "
            "(e.g. use 'options_considered' for comparisons, 'four_pillars' for exactly 4 parallel "
            "items, 'evidence_results' for data with proof points, 'chosen_approach' after weighing "
            "options). You MAY change the modality if it genuinely improves the slide. "
            "If the modality is already correct, focus on restructuring the field values instead."
        )

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=1024,
        temperature=0.3,
        messages=[
            {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content or ""
    improved = _parse_slide_yaml(raw)
    if improved is None:
        slide_num = critique_record.get('slide_number')
        print(
            f"    WARNING: LLM response could not be parsed as YAML for slide {slide_num} — retrying.\n"
            f"    [raw response (first 400 chars)]: {raw[:400]!r}",
            file=sys.stderr,
        )
        # Retry with explicit instruction to return only YAML
        retry_raw_msg = (
            user_msg
            + "\n\nERROR: Your previous response could not be parsed as YAML. "
            "Return ONLY a valid YAML mapping with `modality:` and `fields:` as the only top-level keys. "
            "No prose, no markdown fences, no code blocks, no explanation."
        )
        retry_response = client.chat.completions.create(
            model=model,
            max_completion_tokens=1024,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": retry_raw_msg},
            ],
        )
        raw = retry_response.choices[0].message.content or ""
        improved = _parse_slide_yaml(raw)
        if improved is None:
            print(
                f"    WARNING: retry also failed for slide {slide_num} — keeping original.\n"
                f"    [raw retry (first 400 chars)]: {raw[:400]!r}",
                file=sys.stderr,
            )
            return slide

    improved = _sanitize_slide_fields(improved)

    # Validate required fields; if missing, retry up to 2 more times with an error hint
    from schema_validation import REQUIRED_FIELDS_BY_MODALITY
    for attempt in range(3):
        modality = improved.get("modality", "")
        fields = improved.get("fields") or {}
        required = REQUIRED_FIELDS_BY_MODALITY.get(modality, set())
        missing = required - set(fields.keys())
        if not missing:
            break
        if attempt == 2:
            print(
                f"    WARNING: rewritten slide {critique_record.get('slide_number')} still missing "
                f"fields {sorted(missing)} after 3 attempts — keeping original.",
                file=sys.stderr,
            )
            return slide
        # Retry with explicit error feedback
        retry_msg = (
            user_msg
            + f"\n\nERROR: Your previous response was missing required fields for modality "
            f"'{modality}': {sorted(missing)}. You MUST include them under `fields:`."
        )
        retry_response = client.chat.completions.create(
            model=model,
            max_completion_tokens=1024,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": retry_msg},
            ],
        )
        raw = retry_response.choices[0].message.content or ""
        improved = _parse_slide_yaml(raw)
        if improved is None:
            print(
                f"    WARNING: retry {attempt+1} for slide {critique_record.get('slide_number')} "
                f"could not be parsed — keeping original.",
                file=sys.stderr,
            )
            return slide
        improved = _sanitize_slide_fields(improved)

    # Preserve existing notes (append LLM rewrite marker)
    existing_notes = slide.get("notes", "")
    if existing_notes and "notes" not in improved:
        improved["notes"] = existing_notes

    return improved


# ---------------------------------------------------------------------------
# Main refinement loop
# ---------------------------------------------------------------------------


def run_refinement_loop(
    deck_yaml: Path,
    template: Path,
    output_dir: Path,
    iterations: int,
    model: str,
    rewrite_model: str,
    score_threshold: int,
    catalogue: str,
    provider: str = "auto",
) -> None:
    script_dir = Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "refinement.log"
    tee_out, tee_err = _setup_logging(log_path)
    print(f"[log] Writing full output to: {log_path}\n")

    client = _get_client(provider)
    print(f"[vision model ] {model}")
    print(f"[rewrite model] {rewrite_model}")

    # scores_by_iteration[iter] = {slide_number: score}
    scores_by_iteration: dict[int, dict[int, int]] = {}

    # Track how many consecutive iterations each slide has stayed below threshold
    # Used to trigger modality escalation when a slide is stuck
    slides_stuck: dict[int, int] = {}

    current_yaml = deck_yaml

    for iteration in range(1, iterations + 1):
        print(f"\n{'='*60}")
        print(f"  ITERATION {iteration} of {iterations}")
        print(f"{'='*60}")

        iter_dir = output_dir / f"iteration_{iteration}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        pptx_path = iter_dir / "deck.pptx"
        previews_dir = iter_dir / "previews"
        critique_path = iter_dir / "critique.json"
        revised_yaml_path = iter_dir / "deck.yaml"

        # ---- Step 1: Render YAML → PPTX --------------------------------
        ok = _run(
            [
                sys.executable,
                str(script_dir / "render_from_yaml.py"),
                "--template", str(template),
                "--input", str(current_yaml),
                "--output", str(pptx_path),
                "--catalogue", catalogue,
            ],
            f"[{iteration}] Rendering YAML → {pptx_path.name}",
        )
        if not ok:
            print("Aborting: render failed.", file=sys.stderr)
            sys.exit(1)

        # ---- Step 2: Export slide PNGs ----------------------------------
        ok = _run(
            [
                sys.executable,
                str(script_dir / "render_slide_previews.py"),
                "--input", str(pptx_path),
                "--output-dir", str(previews_dir),
            ],
            f"[{iteration}] Exporting slide previews → {previews_dir}",
        )
        if not ok:
            print("Aborting: preview export failed (is pywin32 installed?).", file=sys.stderr)
            sys.exit(1)

        # ---- Step 3: Vision critique ------------------------------------
        ok = _run(
            [
                sys.executable,
                str(script_dir / "critique_slides.py"),
                "--slides-dir", str(previews_dir),
                "--output", str(critique_path),
                "--model", model,
                "--provider", provider,
            ],
            f"[{iteration}] Vision critique → {critique_path.name}",
        )
        if not ok:
            print("Aborting: critique failed.", file=sys.stderr)
            sys.exit(1)

        # ---- Step 4: LLM rewrite ---------------------------------------
        with open(critique_path, "r", encoding="utf-8") as f:
            critique_records: list[dict] = json.load(f)

        scores = [r["overall_score"] for r in critique_records if "overall_score" in r]
        avg_score = sum(scores) / len(scores) if scores else 0
        low_scoring = [r for r in critique_records if r.get("overall_score", 10) < score_threshold]

        # Track scores for summary table
        scores_by_iteration[iteration] = {
            r["slide_number"]: r["overall_score"]
            for r in critique_records if "overall_score" in r
        }

        print(f"\n[{iteration}] Average score: {avg_score:.1f}/10 — {len(low_scoring)} slides below {score_threshold}")

        deck_spec = _load_yaml(current_yaml)
        slides = deck_spec.get("slides", [])

        by_slide_number = {r["slide_number"]: r for r in critique_records}
        rewritten_count = 0

        for i, slide in enumerate(slides):
            slide_number = i + 1
            record = by_slide_number.get(slide_number)
            if record is None:
                continue
            if record.get("overall_score", 10) >= score_threshold:
                # Slide passed — reset its stuck counter
                slides_stuck.pop(slide_number, None)
                continue

            # Increment stuck counter for this slide
            slides_stuck[slide_number] = slides_stuck.get(slide_number, 0) + 1
            escalate = slides_stuck[slide_number] >= 2

            if escalate:
                print(
                    f"  Rewriting slide {slide_number} (score {record['overall_score']}/10, "
                    f"stuck {slides_stuck[slide_number]} iterations — escalating modality)..."
                )
            else:
                print(f"  Rewriting slide {slide_number} (score {record['overall_score']}/10)...")

            slides[i] = rewrite_slide_with_llm(
                client, rewrite_model, slide, record, escalate_modality=escalate
            )
            rewritten_count += 1

        print(f"[{iteration}] Rewrote {rewritten_count} slides.")

        deck_spec["slides"] = slides
        _save_yaml(deck_spec, revised_yaml_path)
        print(f"[{iteration}] Revised YAML saved → {revised_yaml_path}")

        current_yaml = revised_yaml_path

        # Early exit if all slides are already good enough
        if not low_scoring:
            print(f"\nAll slides scored >= {score_threshold}. Stopping early after iteration {iteration}.")
            break

    # ---- Final render ---------------------------------------------------
    print(f"\n{'='*60}")
    print("  FINAL RENDER")
    print(f"{'='*60}")

    final_pptx = output_dir / "deck_final.pptx"
    final_yaml = output_dir / "deck_final.yaml"

    shutil.copy(current_yaml, final_yaml)

    ok = _run(
        [
            sys.executable,
            str(script_dir / "render_from_yaml.py"),
            "--template", str(template),
            "--input", str(final_yaml),
            "--output", str(final_pptx),
            "--catalogue", catalogue,
        ],
        f"Final render → {final_pptx.name}",
    )
    if ok:
        print(f"\nDone. Final artefacts:")
        print(f"  PPTX : {final_pptx}")
        print(f"  YAML : {final_yaml}")
        print(f"  LOG  : {log_path}")

        # ---- Score comparison table ------------------------------------
        if scores_by_iteration:
            iter_nums = sorted(scores_by_iteration.keys())
            first_iter = iter_nums[0]
            last_iter = iter_nums[-1]
            all_slides = sorted(
                set(sn for it in scores_by_iteration.values() for sn in it.keys())
            )

            col_w = 8
            header_iters = [f"It.{n}" for n in iter_nums]
            if first_iter != last_iter:
                header_iters.append("Delta")
            header = f"{'Slide':>6}  " + "  ".join(f"{h:>{col_w}}" for h in header_iters)
            sep = "-" * len(header)

            print(f"\n{'='*60}")
            print("  SCORE SUMMARY")
            print(f"{'='*60}")
            print(header)
            print(sep)

            for sn in all_slides:
                row = f"{sn:>6}  "
                first_score = scores_by_iteration[first_iter].get(sn)
                last_score = scores_by_iteration[last_iter].get(sn)
                cells = []
                for it in iter_nums:
                    sc = scores_by_iteration[it].get(sn)
                    cells.append(f"{sc:>{col_w}}" if sc is not None else f"{'—':>{col_w}}")
                if first_iter != last_iter and first_score is not None and last_score is not None:
                    delta = last_score - first_score
                    sign = "+" if delta > 0 else ""
                    cells.append(f"{sign}{delta:>{col_w-1}}")
                print(row + "  ".join(cells))

            print(sep)
            # Averages row
            avg_cells = []
            for it in iter_nums:
                vals = list(scores_by_iteration[it].values())
                avg = sum(vals) / len(vals) if vals else 0
                avg_cells.append(f"{avg:>{col_w}.1f}")
            if first_iter != last_iter:
                v0 = list(scores_by_iteration[first_iter].values())
                vn = list(scores_by_iteration[last_iter].values())
                a0 = sum(v0) / len(v0) if v0 else 0
                an = sum(vn) / len(vn) if vn else 0
                delta_avg = an - a0
                sign = "+" if delta_avg > 0 else ""
                avg_cells.append(f"{sign}{delta_avg:>{col_w-1}.1f}")
            print(f"{'AVG':>6}  " + "  ".join(avg_cells))
    else:
        print("Final render failed.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated render → critique → rewrite refinement loop"
    )
    parser.add_argument("--deck", required=True, help="Input YAML deck spec")
    parser.add_argument("--template", required=True, help="Path to .potx template")
    parser.add_argument(
        "--output-dir",
        default="refined",
        help="Directory to write all iteration outputs (default: refined/)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of refinement iterations (default: 3)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="Vision model for slide critique (default: gpt-4.1)",
    )
    parser.add_argument(
        "--rewrite-model",
        default="gpt-5.4-nano",
        help="Text model for YAML rewrite — cheaper, no vision needed (default: gpt-5.4-nano)",
    )
    parser.add_argument(
        "--score-threshold",
        type=int,
        default=7,
        help="Slides scoring below this are rewritten (default: 7)",
    )
    parser.add_argument(
        "--catalogue",
        default="visual_family_registry.yaml",
        help="Path to visual family registry YAML (default: visual_family_registry.yaml)",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "azure", "openai", "github"],
        default="auto",
        help="LLM provider: auto (default), azure (OPENAI_API_KEY+AZURE_OPENAI_ENDPOINT), openai, github",
    )
    args = parser.parse_args()

    run_refinement_loop(
        deck_yaml=Path(args.deck),
        template=Path(args.template),
        output_dir=Path(args.output_dir),
        iterations=args.iterations,
        model=args.model,
        rewrite_model=args.rewrite_model,
        score_threshold=args.score_threshold,
        catalogue=args.catalogue,
        provider=args.provider,
    )


if __name__ == "__main__":
    main()
