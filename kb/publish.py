"""
KB Publish — Batch rendering CLI for carousel visuals.

Finds transcripts with linkedin_v2 analysis output, renders them
as PDF carousels with optional mermaid diagrams.

Usage (via kb command):
    kb publish --pending         # Render all approved posts without visuals
    kb publish --regenerate      # Re-render all existing visuals
    kb publish --dry-run         # Show what would be rendered
    kb publish --decimal 50.01.01  # Render specific decimal
"""

import json
import logging
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kb.config import load_config, get_paths

console = Console()
logger = logging.getLogger(__name__)

# Load paths from config
_config = load_config()
_paths = get_paths(_config)
KB_ROOT = _paths["kb_output"]


def find_renderables(
    decimal_filter: str | None = None,
    include_rendered: bool = False,
) -> list[dict]:
    """
    Find transcripts that have carousel_slides analysis and can be rendered.

    Args:
        decimal_filter: Restrict to a specific decimal prefix.
        include_rendered: If True, include transcripts that already have visuals.

    Returns:
        List of dicts with keys: path, title, decimal, has_visuals, slides_data
    """
    renderables = []

    for decimal_dir in sorted(KB_ROOT.iterdir()):
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue
        if decimal_filter and not decimal_dir.name.startswith(decimal_filter):
            continue

        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)

                analysis = data.get("analysis", {})

                # Need carousel_slides to render
                carousel_slides = analysis.get("carousel_slides")
                if not carousel_slides:
                    continue

                # Check if slides data is present
                slides_output = carousel_slides.get("output", carousel_slides)
                if isinstance(slides_output, str):
                    try:
                        slides_output = json.loads(slides_output)
                    except (json.JSONDecodeError, TypeError):
                        continue

                if not isinstance(slides_output, dict) or "slides" not in slides_output:
                    continue

                # Check for existing visuals
                visuals_dir = decimal_dir / "visuals"
                has_visuals = (
                    visuals_dir.exists()
                    and (visuals_dir / "carousel.pdf").exists()
                )

                if not include_rendered and has_visuals:
                    continue

                # Also check for linkedin_v2
                has_linkedin_v2 = "linkedin_v2" in analysis

                renderables.append({
                    "path": str(json_file),
                    "title": data.get("title", json_file.stem),
                    "decimal": decimal_dir.name,
                    "has_visuals": has_visuals,
                    "has_linkedin_v2": has_linkedin_v2,
                    "slides_data": slides_output,
                    "visuals_dir": str(visuals_dir),
                })

            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                logger.warning("Could not read %s: %s", json_file, e)

    return renderables


def find_staged_renderables(
    decimal_filter: str | None = None,
) -> list[dict]:
    """
    Find staged/ready items from action-state.json that have carousel_slides.

    Uses the curation workflow state to find items that have been staged
    (and possibly edited) and are ready for rendering.

    Args:
        decimal_filter: Restrict to a specific decimal prefix.

    Returns:
        List of dicts with keys: path, title, decimal, has_visuals, slides_data, visuals_dir
    """
    from kb.serve import load_action_state, ACTION_ID_SEP

    state = load_action_state()
    renderables = []

    for action_id, action_data in state.get("actions", {}).items():
        status = action_data.get("status", "")
        if status not in ("staged", "ready"):
            continue

        # Parse action_id
        parts = action_id.split(ACTION_ID_SEP)
        if len(parts) != 2:
            continue

        transcript_id = parts[0]

        # Find transcript file
        for decimal_dir in sorted(KB_ROOT.iterdir()):
            if not decimal_dir.is_dir():
                continue
            if decimal_dir.name in ("config", "examples"):
                continue
            if decimal_filter and not decimal_dir.name.startswith(decimal_filter):
                continue

            for json_file in decimal_dir.glob("*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)

                    if data.get("id") != transcript_id:
                        continue

                    analysis = data.get("analysis", {})
                    carousel_slides = analysis.get("carousel_slides")
                    if not carousel_slides:
                        continue

                    # Check slides data
                    slides_output = carousel_slides.get("output", carousel_slides)
                    if isinstance(slides_output, str):
                        try:
                            slides_output = json.loads(slides_output)
                        except (json.JSONDecodeError, TypeError):
                            continue

                    if not isinstance(slides_output, dict) or "slides" not in slides_output:
                        continue

                    visuals_dir = decimal_dir / "visuals"
                    has_visuals = (
                        visuals_dir.exists()
                        and (visuals_dir / "carousel.pdf").exists()
                    )

                    renderables.append({
                        "path": str(json_file),
                        "title": data.get("title", json_file.stem),
                        "decimal": decimal_dir.name,
                        "has_visuals": has_visuals,
                        "has_linkedin_v2": "linkedin_v2" in analysis,
                        "slides_data": slides_output,
                        "visuals_dir": str(visuals_dir),
                    })

                except (json.JSONDecodeError, KeyError, AttributeError) as e:
                    logger.warning("Could not read %s: %s", json_file, e)

    return renderables


def render_one(renderable: dict, dry_run: bool = False, template_name: str | None = None) -> dict:
    """
    Render a single transcript's carousel.

    Args:
        renderable: Dict from find_renderables()
        dry_run: If True, don't actually render.
        template_name: Template name override (None uses config default).

    Returns:
        Dict with result info.
    """
    from kb.render import render_pipeline

    title = renderable["title"]
    output_dir = renderable["visuals_dir"]
    slides_data = renderable["slides_data"]

    if dry_run:
        slide_count = len(slides_data.get("slides", []))
        has_mermaid = slides_data.get("has_mermaid", False)
        return {
            "title": title,
            "status": "dry_run",
            "slides": slide_count,
            "has_mermaid": has_mermaid,
            "output_dir": output_dir,
        }

    try:
        result = render_pipeline(slides_data, output_dir, template_name=template_name)
        return {
            "title": title,
            "status": "success" if result.get("pdf_path") else "failed",
            "pdf_path": result.get("pdf_path"),
            "thumbnail_count": len(result.get("thumbnail_paths", [])),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error("Render failed for %s: %s", title, e)
        return {
            "title": title,
            "status": "error",
            "error": str(e),
        }


def main():
    """CLI entry point for kb publish."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="kb publish",
        description="Render carousel visuals for approved posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kb publish --pending              # Render posts without visuals
  kb publish --regenerate           # Re-render all existing visuals
  kb publish --dry-run              # Preview what would be rendered
  kb publish --decimal 50.01.01     # Render specific decimal only
        """,
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Render all transcripts with carousel_slides but no visuals",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Re-render all existing visuals with current templates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be rendered without doing it",
    )
    parser.add_argument(
        "--decimal", "-d",
        type=str,
        help="Filter to specific decimal prefix",
    )
    parser.add_argument(
        "--template", "-t",
        type=str,
        help="Template name (e.g. brand-purple, modern-editorial, tech-minimal)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Render staged items (uses latest edited content from curation workflow)",
    )

    args = parser.parse_args()

    # Default to --pending if no mode specified
    if not args.pending and not args.regenerate and not args.staged:
        args.pending = True

    include_rendered = args.regenerate

    console.print(
        Panel("[bold]KB Publish — Carousel Renderer[/bold]", border_style="cyan")
    )

    # Find renderables: either staged items or standard scan
    if args.staged:
        renderables = find_staged_renderables(decimal_filter=args.decimal)
    else:
        renderables = find_renderables(
            decimal_filter=args.decimal,
            include_rendered=include_rendered,
        )

    if not renderables:
        console.print("[green]No transcripts to render.[/green]")
        if not include_rendered:
            console.print(
                "[dim]Tip: Use --regenerate to re-render existing visuals.[/dim]"
            )
        return

    # Show what will be rendered
    table = Table(title="Transcripts to render", show_header=True)
    table.add_column("Decimal", style="cyan")
    table.add_column("Title")
    table.add_column("Slides", justify="right")
    table.add_column("Mermaid")
    table.add_column("Status")

    for r in renderables:
        slides = r["slides_data"].get("slides", [])
        has_mermaid = r["slides_data"].get("has_mermaid", False)
        status = "[yellow]has visuals[/yellow]" if r["has_visuals"] else "[dim]pending[/dim]"

        table.add_row(
            r["decimal"],
            r["title"][:50],
            str(len(slides)),
            "Yes" if has_mermaid else "No",
            status,
        )

    console.print(table)
    console.print(f"\n[bold]{len(renderables)} transcript(s) to render.[/bold]")

    if args.template:
        console.print(f"[bold]Template:[/bold] {args.template}")

    if args.dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        for r in renderables:
            result = render_one(r, dry_run=True)
            console.print(
                f"  [cyan]{r['decimal']}[/cyan] {result['title']}: "
                f"{result['slides']} slides, "
                f"mermaid={'yes' if result['has_mermaid'] else 'no'}, "
                f"→ {result['output_dir']}"
            )
        return

    # Render each
    success = 0
    failed = 0

    for i, r in enumerate(renderables, 1):
        console.print(
            f"\n[bold cyan]({i}/{len(renderables)}) {r['title']}[/bold cyan]"
        )
        result = render_one(r, template_name=args.template)

        if result["status"] == "success":
            success += 1
            console.print(
                f"  [green]PDF: {result['pdf_path']}[/green]"
            )
            console.print(
                f"  [green]{result['thumbnail_count']} thumbnails[/green]"
            )
            if result.get("errors"):
                for err in result["errors"]:
                    console.print(f"  [yellow]Warning: {err}[/yellow]")
        else:
            failed += 1
            error = result.get("error", "Unknown error")
            console.print(f"  [red]Failed: {error}[/red]")

    console.print(
        f"\n[bold green]Done! {success} rendered, {failed} failed.[/bold green]"
    )
