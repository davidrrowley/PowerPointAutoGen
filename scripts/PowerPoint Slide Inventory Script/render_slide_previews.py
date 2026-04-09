"""
render_slide_previews.py
------------------------
Export every slide in a .pptx file to PNG images using PowerPoint COM automation.

Requirements:
    pip install pywin32

Usage:
    python render_slide_previews.py --input deck.pptx --output-dir previews/ [--width 1920]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def export_slides_via_com(pptx_path: Path, output_dir: Path, width: int = 1920) -> list[Path]:
    """
    Use PowerPoint COM automation to export each slide as a PNG.
    Returns list of exported PNG paths in slide order.
    """
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is required for slide rendering on Windows.\n"
            "Install with: pip install pywin32\n"
            "Then run: python -m pywin32_postinstall -install"
        ) from exc

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pptx_abs = str(pptx_path.resolve())

    ppt_app = None
    presentation = None
    exported: list[Path] = []

    try:
        # Start PowerPoint — some installations reject Visible=False, so we
        # open without a window and minimise on a best-effort basis.
        ppt_app = win32com.client.Dispatch("PowerPoint.Application")
        time.sleep(1)  # give PowerPoint a moment to fully initialise
        try:
            ppt_app.WindowState = 2  # ppWindowMinimized
        except Exception:
            pass

        # RPC_E_CALL_REJECTED on Open if PowerPoint is still busy — retry with backoff
        for _open_attempt in range(6):
            try:
                presentation = ppt_app.Presentations.Open(
                    pptx_abs,
                    ReadOnly=True,
                    Untitled=False,
                    WithWindow=False,
                )
                break
            except Exception as _open_err:
                if _open_attempt == 5:
                    raise
                wait = 2 ** _open_attempt  # 1, 2, 4, 8, 16 seconds
                print(f"  COM busy opening file, retrying in {wait}s... ({_open_err})")
                time.sleep(wait)

        slide_count = presentation.Slides.Count
        print(f"Exporting {slide_count} slides from: {pptx_abs}")

        # PowerPoint Export uses points; target width in px at 96dpi
        # We scale: height = width * (slide height / slide width)
        slide_width_pts = presentation.PageSetup.SlideWidth
        slide_height_pts = presentation.PageSetup.SlideHeight
        aspect = slide_height_pts / slide_width_pts
        height = int(width * aspect)

        for i in range(1, slide_count + 1):
            out_path = output_dir / f"slide_{i:03d}.png"
            # RPC_E_CALL_REJECTED (-2147418111): PowerPoint busy — retry with backoff
            for attempt in range(5):
                try:
                    presentation.Slides(i).Export(str(out_path), "PNG", width, height)
                    break
                except Exception as com_err:
                    if attempt == 4:
                        raise
                    wait = 2 ** attempt  # 1, 2, 4, 8 seconds
                    print(f"  COM busy on slide {i}, retrying in {wait}s... ({com_err})")
                    time.sleep(wait)
            exported.append(out_path)
            print(f"  Exported slide {i}/{slide_count} -> {out_path.name}")

    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if ppt_app is not None:
            try:
                ppt_app.Quit()
            except Exception:
                pass
        # Give COM a moment to release
        time.sleep(0.5)

    return exported


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PPTX slides to PNG images using PowerPoint COM"
    )
    parser.add_argument("--input", required=True, help="Path to .pptx file")
    parser.add_argument(
        "--output-dir",
        default="slide_previews",
        help="Directory to write PNGs into (default: slide_previews/)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Export width in pixels (default: 1920)",
    )
    args = parser.parse_args()

    pptx_path = Path(args.input)
    if not pptx_path.exists():
        print(f"ERROR: Input file not found: {pptx_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    exported = export_slides_via_com(pptx_path, output_dir, width=args.width)

    print(f"\nDone. Exported {len(exported)} PNG files to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

