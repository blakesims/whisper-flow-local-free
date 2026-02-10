"""Visual pipeline for KB serve dashboard.

Handles carousel rendering in background threads.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

from kb.serve_state import load_action_state, save_action_state
from kb.serve_scanner import ACTION_ID_SEP

logger = logging.getLogger(__name__)


def _update_visual_status(action_id: str, visual_status: str, visual_data: dict | None = None):
    """Update visual_status for an action in action-state.json (thread-safe)."""
    state = load_action_state()
    if action_id in state["actions"]:
        state["actions"][action_id]["visual_status"] = visual_status
        if visual_data:
            state["actions"][action_id]["visual_data"] = visual_data
        save_action_state(state)


def _find_transcript_file(action_id: str, kb_root=None) -> Path | None:
    """Find transcript JSON file from action_id (format: transcript_id--analysis_type).

    Args:
        action_id: The action ID to look up.
        kb_root: KB root path. If None, lazy-imports from kb.serve.
    """
    if kb_root is None:
        from kb.serve import KB_ROOT
        kb_root = KB_ROOT

    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return None
    transcript_id = parts[0]

    for decimal_dir in kb_root.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue
        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                if data.get("id") == transcript_id:
                    return json_file
            except (json.JSONDecodeError, IOError):
                continue
    return None


def run_visual_pipeline(action_id: str, transcript_path: str, template_name: str = None):
    """
    Run the full visual pipeline in a background thread.

    Steps:
    1. Run visual_format classifier
    2. If CAROUSEL: run carousel_slides analysis
    3. If CAROUSEL: render pipeline (HTML -> PDF + thumbnails)
    4. Update visual_status in action-state.json
    """
    try:
        _update_visual_status(action_id, "generating")

        with open(transcript_path) as f:
            transcript_data = json.load(f)

        existing_analysis = transcript_data.get("analysis", {})
        transcript_text = transcript_data.get("transcript", "")
        title = transcript_data.get("title", "")
        decimal = transcript_data.get("decimal", "")

        # Lazy import to avoid circular/heavy imports at module level
        from kb.analyze import run_analysis_with_deps, analyze_transcript_file, _save_analysis_to_file, DEFAULT_MODEL

        model = DEFAULT_MODEL

        # Step 1: Run visual_format classifier (requires linkedin_v2)
        if "visual_format" not in existing_analysis:
            logger.info("[Visual Pipeline] Running visual_format for %s", action_id)
            try:
                vf_result, vf_prereqs = run_analysis_with_deps(
                    transcript_data=transcript_data,
                    analysis_type="visual_format",
                    model=model,
                    existing_analysis=existing_analysis,
                )
                if "error" not in vf_result:
                    vf_result["_model"] = model
                    vf_result["_analyzed_at"] = datetime.now().isoformat()
                    existing_analysis["visual_format"] = vf_result
                    _save_analysis_to_file(transcript_path, transcript_data, existing_analysis)
            except Exception as e:
                logger.error("[Visual Pipeline] visual_format failed: %s", e)
                _update_visual_status(action_id, "failed", {"error": f"visual_format failed: {e}"})
                return

        visual_format = existing_analysis.get("visual_format", {})

        # Determine format type from visual_format output
        format_type = visual_format.get("format", visual_format.get("visual_format", "TEXT_ONLY"))
        if isinstance(format_type, str):
            format_type = format_type.upper()

        if format_type != "CAROUSEL":
            # TEXT_ONLY — no visuals to generate
            logger.info("[Visual Pipeline] TEXT_ONLY for %s — no visuals needed", action_id)
            _update_visual_status(action_id, "text_only", {"format": "TEXT_ONLY"})
            return

        # Step 2: Run carousel_slides analysis (requires linkedin_v2)
        if "carousel_slides" not in existing_analysis:
            logger.info("[Visual Pipeline] Running carousel_slides for %s", action_id)
            try:
                cs_result, cs_prereqs = run_analysis_with_deps(
                    transcript_data=transcript_data,
                    analysis_type="carousel_slides",
                    model=model,
                    existing_analysis=existing_analysis,
                )
                if "error" not in cs_result:
                    cs_result["_model"] = model
                    cs_result["_analyzed_at"] = datetime.now().isoformat()
                    existing_analysis["carousel_slides"] = cs_result
                    _save_analysis_to_file(transcript_path, transcript_data, existing_analysis)
            except Exception as e:
                logger.error("[Visual Pipeline] carousel_slides failed: %s", e)
                _update_visual_status(action_id, "failed", {"error": f"carousel_slides failed: {e}"})
                return

        # Step 3: Render carousel (HTML -> PDF + thumbnails)
        carousel_slides = existing_analysis.get("carousel_slides", {})
        # Extract slides data — handle nested output format
        slides_output = carousel_slides.get("output", carousel_slides)
        if isinstance(slides_output, str):
            try:
                slides_output = json.loads(slides_output)
            except (json.JSONDecodeError, TypeError):
                _update_visual_status(action_id, "failed", {"error": "carousel_slides output not parseable"})
                return

        if not isinstance(slides_output, dict) or "slides" not in slides_output:
            # Try top-level slides key
            if "slides" in carousel_slides:
                slides_output = {"slides": carousel_slides["slides"],
                                "total_slides": carousel_slides.get("total_slides", len(carousel_slides["slides"])),
                                "has_mermaid": carousel_slides.get("has_mermaid", False)}
            else:
                _update_visual_status(action_id, "failed", {"error": "No slides data in carousel_slides"})
                return

        # Build output dir
        decimal_dir = Path(transcript_path).parent
        visuals_dir = decimal_dir / "visuals"

        logger.info("[Visual Pipeline] Rendering carousel for %s -> %s", action_id, visuals_dir)

        from kb.render import render_pipeline
        result = render_pipeline(slides_output, str(visuals_dir), template_name=template_name)

        if result.get("pdf_path"):
            # Make paths relative to KB_ROOT for serving
            visual_data = {
                "format": "CAROUSEL",
                "pdf_path": result["pdf_path"],
                "thumbnail_paths": result.get("thumbnail_paths", []),
                "errors": result.get("errors", []),
            }
            _update_visual_status(action_id, "ready", visual_data)
            logger.info("[Visual Pipeline] Carousel ready for %s: %s", action_id, result["pdf_path"])
        else:
            _update_visual_status(action_id, "failed", {
                "error": "Carousel render produced no PDF",
                "errors": result.get("errors", []),
            })

    except Exception as e:
        logger.error("[Visual Pipeline] Unexpected error for %s: %s", action_id, e)
        _update_visual_status(action_id, "failed", {"error": str(e)})
