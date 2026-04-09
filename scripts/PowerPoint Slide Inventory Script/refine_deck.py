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
- Following IBM Consulting presentation standards (IBM Blue accents, Arial font, ≤5 bullets, ≤120 chars per bullet, ≤14-word title)
- Returning ONLY a valid YAML block for that single slide — no prose, no code fences, no extra keys

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


def _parse_slide_yaml(raw: str) -> dict | None:
    """Parse LLM response as a YAML slide mapping, stripping code fences if present."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
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
    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict) and "modality" in parsed:
            return parsed
    except yaml.YAMLError:
        pass
    return None


# ---------------------------------------------------------------------------
# Core rewrite step
# ---------------------------------------------------------------------------


def rewrite_slide_with_llm(
    client,
    model: str,
    slide: dict,
    critique_record: dict,
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
        print(
            f"    WARNING: LLM response could not be parsed as YAML for slide "
            f"{critique_record.get('slide_number')} — keeping original.",
            file=sys.stderr,
        )
        return slide

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

    client = _get_client(provider)
    print(f"[vision model ] {model}")
    print(f"[rewrite model] {rewrite_model}")

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
                continue

            print(f"  Rewriting slide {slide_number} (score {record['overall_score']}/10)...")
            slides[i] = rewrite_slide_with_llm(client, rewrite_model, slide, record)
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
