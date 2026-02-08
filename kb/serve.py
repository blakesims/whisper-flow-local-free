#!/usr/bin/env python3
"""
KB Serve - Action Queue Dashboard

Flask server that displays actionable outputs from the knowledge base
for copy/sharing. Implements polling-based updates with client-side
clipboard and pyperclip fallback.

Usage:
    kb serve              # Start on default port 8765
    kb serve --port 9000  # Start on custom port
"""

import sys
import os
import json
import logging
import re
import shutil
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import Flask, render_template, jsonify, request, send_from_directory
import pyperclip

from kb.videos import (
    load_inventory, save_inventory, scan_videos, INVENTORY_PATH,
    queue_transcription, get_queue_status, start_worker, load_queue
)
from kb.analyze import list_analysis_types, load_analysis_type, ANALYSIS_TYPES_DIR, AUTO_JUDGE_TYPES

logger = logging.getLogger(__name__)

# Action ID separator (using -- to avoid URL encoding issues with ::)
ACTION_ID_SEP = "--"
# Regex for validating action IDs: transcript_id--analysis_name
ACTION_ID_PATTERN = re.compile(r'^[\w\.\-]+--[a-z0-9_]+$')

# Pattern to match versioned analysis keys that should be filtered from scan results.
# These are internal storage keys, not actionable items.
# Built from AUTO_JUDGE_TYPES to only match known versioned prefixes:
# - linkedin_v2_0, linkedin_v2_1, ... (versioned drafts)
# - linkedin_judge_0, linkedin_judge_1, ... (versioned judge evaluations)
# - linkedin_v2_1_0, linkedin_v2_2_1, ... (edit sub-versions)
def _build_versioned_key_pattern():
    """Build regex pattern from AUTO_JUDGE_TYPES to match versioned keys."""
    prefixes = set()
    for analysis_type, judge_type in AUTO_JUDGE_TYPES.items():
        prefixes.add(re.escape(analysis_type))
        prefixes.add(re.escape(judge_type))
    prefix_group = "|".join(sorted(prefixes))
    # Match: prefix_N or prefix_N_N (versioned drafts, judges, and edit sub-versions)
    return re.compile(rf'^(?:{prefix_group})_\d+(?:_\d+)?$')

VERSIONED_KEY_PATTERN = _build_versioned_key_pattern()

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.__main__ import load_config, get_paths

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
ACTION_STATE_PATH = Path.home() / ".kb" / "action-state.json"
PROMPT_FEEDBACK_PATH = Path.home() / ".kb" / "prompt-feedback.json"

def get_action_mapping() -> dict:
    """Load action mapping from config with pattern support.

    Supports three pattern types:
    - Plain: "skool_post" matches any input type
    - Typed: "meeting.student_guide" matches only meeting input type
    - Wildcard: "*.summary" matches all input types

    Returns dict mapping (input_type, analysis_type) tuples to destination labels.
    """
    serve_config = _config.get("serve", {})
    raw_mapping = serve_config.get("action_mapping", {})

    # Store as structured mapping for efficient lookup
    # Keys are tuples: (input_type or None, analysis_type)
    # Wildcard patterns stored with input_type="*"
    structured = {}

    for pattern, destination in raw_mapping.items():
        if "." in pattern:
            # Either typed (meeting.guide) or wildcard (*.summary)
            parts = pattern.split(".", 1)
            input_type, analysis_type = parts[0], parts[1]
            structured[(input_type, analysis_type)] = destination
        else:
            # Plain pattern - matches any input type
            structured[(None, pattern)] = destination

    return structured


def get_destination_for_action(input_type: str, analysis_type: str, mapping: dict) -> Optional[str]:
    """Get destination label for an (input_type, analysis_type) pair.

    Priority:
    1. Exact match: (input_type, analysis_type)
    2. Wildcard match: ("*", analysis_type)
    3. Plain match: (None, analysis_type)
    """
    # Try exact match first
    key = (input_type, analysis_type)
    if key in mapping:
        return mapping[key]

    # Try wildcard
    wildcard_key = ("*", analysis_type)
    if wildcard_key in mapping:
        return mapping[wildcard_key]

    # Try plain (any input type)
    plain_key = (None, analysis_type)
    if plain_key in mapping:
        return mapping[plain_key]

    return None

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))


# --- Action State Management ---

def load_action_state() -> dict:
    """Load action state from ~/.kb/action-state.json.

    If the file is corrupted, backs it up and returns empty state.
    """
    if not ACTION_STATE_PATH.exists():
        return {"actions": {}}

    try:
        with open(ACTION_STATE_PATH) as f:
            state = json.load(f)

        # Validate structure
        if not isinstance(state, dict) or "actions" not in state:
            raise ValueError("Invalid state structure")

        return state
    except (json.JSONDecodeError, IOError, ValueError) as e:
        # Backup corrupted file before resetting
        if ACTION_STATE_PATH.exists():
            backup_path = ACTION_STATE_PATH.with_suffix('.backup')
            shutil.copy(ACTION_STATE_PATH, backup_path)
            print(f"[KB Serve] Warning: Corrupted action state file, backup saved to {backup_path}")

        return {"actions": {}}


def save_action_state(state: dict):
    """Save action state to ~/.kb/action-state.json."""
    ACTION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACTION_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def migrate_approved_to_draft() -> int:
    """Reset existing approved items to draft state.

    One-time migration for T023: all previously approved items are reset
    to 'draft' so they go through the new iteration workflow. The approval
    timestamp is preserved in '_previously_approved_at'.

    Returns:
        Number of items migrated.
    """
    state = load_action_state()
    count = 0
    for action_id, action_data in state.get("actions", {}).items():
        if action_data.get("status") == "approved":
            action_data["_previously_approved_at"] = action_data.get("completed_at", "")
            action_data["status"] = "draft"
            action_data.pop("completed_at", None)
            count += 1
    if count > 0:
        save_action_state(state)
        logger.info("Migrated %d approved items to draft state", count)
    return count


# --- Prompt Feedback Storage ---

def load_prompt_feedback() -> dict:
    """Load prompt feedback from ~/.kb/prompt-feedback.json.

    Returns dict with 'flags' list. Creates empty structure if file doesn't exist.
    """
    if not PROMPT_FEEDBACK_PATH.exists():
        return {"flags": []}

    try:
        with open(PROMPT_FEEDBACK_PATH) as f:
            feedback = json.load(f)

        # Validate structure
        if not isinstance(feedback, dict) or "flags" not in feedback:
            return {"flags": []}

        return feedback
    except (json.JSONDecodeError, IOError):
        return {"flags": []}


def save_prompt_feedback(feedback: dict):
    """Save prompt feedback to ~/.kb/prompt-feedback.json."""
    PROMPT_FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPT_FEEDBACK_PATH, 'w') as f:
        json.dump(feedback, f, indent=2)


# --- Visual Pipeline (Background Thread) ---

def _update_visual_status(action_id: str, visual_status: str, visual_data: dict | None = None):
    """Update visual_status for an action in action-state.json (thread-safe)."""
    state = load_action_state()
    if action_id in state["actions"]:
        state["actions"][action_id]["visual_status"] = visual_status
        if visual_data:
            state["actions"][action_id]["visual_data"] = visual_data
        save_action_state(state)


def _find_transcript_file(action_id: str) -> Path | None:
    """Find transcript JSON file from action_id (format: transcript_id--analysis_type)."""
    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return None
    transcript_id = parts[0]

    for decimal_dir in KB_ROOT.iterdir():
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


def run_visual_pipeline(action_id: str, transcript_path: str):
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
        result = render_pipeline(slides_output, str(visuals_dir))

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


# --- KB Scanning for Actionable Items ---

def scan_actionable_items() -> list[dict]:
    """
    Scan all transcript JSON files in KB_ROOT for actionable analyses.

    Returns list of action items with metadata.
    """
    action_mapping = get_action_mapping()
    action_items = []

    # Scan all decimal directories
    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue

        # Find all JSON files
        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)

                # Get input_type for pattern matching
                input_type = data.get("source", {}).get("type", "unknown")

                # Check for actionable analyses
                analysis = data.get("analysis", {})
                for analysis_name in analysis.keys():
                    # Skip versioned keys (internal storage, not actionable)
                    if VERSIONED_KEY_PATTERN.match(analysis_name):
                        continue

                    destination = get_destination_for_action(input_type, analysis_name, action_mapping)
                    if destination is None:
                        continue  # Not actionable

                    analysis_data = analysis[analysis_name]

                    # Generate action ID: transcript_id--analysis_name
                    action_id = f"{data.get('id', json_file.stem)}{ACTION_ID_SEP}{analysis_name}"

                    # Get content (handle various formats)
                    analyzed_at = ""
                    model = ""

                    if isinstance(analysis_data, dict):
                        # Try to get the inner content (e.g., guide.guide or summary.summary)
                        inner = analysis_data.get(analysis_name)
                        analyzed_at = analysis_data.get("_analyzed_at", "")
                        model = analysis_data.get("_model", "")

                        if inner is None:
                            # Check for 'post' field (e.g., linkedin_post)
                            if "post" in analysis_data:
                                content = analysis_data["post"]
                            else:
                                # No nested key, use the whole dict as content
                                content = json.dumps(analysis_data, indent=2, ensure_ascii=False)
                        elif isinstance(inner, str):
                            content = inner
                        elif isinstance(inner, dict):
                            # Structured output (like guide with title, steps, etc.)
                            content = json.dumps(inner, indent=2, ensure_ascii=False)
                        else:
                            content = str(inner)
                    else:
                        content = str(analysis_data)

                    # Build raw_data: analysis dict minus _ prefixed metadata keys
                    if isinstance(analysis_data, dict):
                        raw_data = {k: v for k, v in analysis_data.items() if not k.startswith("_")}
                    else:
                        raw_data = None

                    # Calculate word count (handle both string and fallback)
                    if isinstance(content, str):
                        word_count = len(content.split()) if content else 0
                    else:
                        content = str(content)
                        word_count = len(content.split())

                    action_items.append({
                        "id": action_id,
                        "type": analysis_name,
                        "destination": destination,
                        "source_title": data.get("title", "Untitled"),
                        "source_decimal": data.get("decimal", ""),
                        "content": content,
                        "raw_data": raw_data,
                        "word_count": word_count,
                        "analyzed_at": analyzed_at,
                        "model": model,
                        "transcript_path": str(json_file),
                    })

            except (json.JSONDecodeError, KeyError, IOError) as e:
                # Skip malformed files
                continue

    return action_items


def get_action_status(action_id: str, state: dict) -> dict:
    """Get status info for an action."""
    action_state = state["actions"].get(action_id, {})
    return {
        "status": action_state.get("status", "pending"),
        "copied_count": action_state.get("copied_count", 0),
        "created_at": action_state.get("created_at", ""),
        "completed_at": action_state.get("completed_at", ""),
    }


def format_relative_time(iso_timestamp: str) -> str:
    """Format ISO timestamp as relative time (e.g., '2 hours ago')."""
    if not iso_timestamp:
        return "Unknown"

    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = now - dt

        if delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"
    except (ValueError, AttributeError):
        return "Unknown"


# --- Flask Routes ---

@app.route('/')
def index():
    """Main dashboard HTML."""
    return render_template('action_queue.html')


@app.route('/posting-queue')
def posting_queue():
    """Posting queue HTML - shows approved items ready to post."""
    return render_template('posting_queue.html')


@app.route('/api/queue')
def get_queue():
    """List pending/completed actions."""
    state = load_action_state()
    items = scan_actionable_items()

    # Enrich items with state
    pending = []
    completed = []

    for item in items:
        item_state = get_action_status(item["id"], state)
        item["status"] = item_state["status"]
        item["copied_count"] = item_state["copied_count"]
        item["relative_time"] = format_relative_time(item["analyzed_at"])

        if item_state["status"] == "pending":
            pending.append(item)
        elif item_state["status"] == "approved":
            # Approved items go to posting queue, not main queue
            pass
        elif item_state["status"] in ("done", "skipped", "posted"):
            item["completed_at"] = item_state.get("completed_at") or item_state.get("posted_at", "")

            # Only show items completed today
            if item["completed_at"]:
                try:
                    completed_dt = datetime.fromisoformat(item["completed_at"])
                    if completed_dt.date() == datetime.now().date():
                        completed.append(item)
                except ValueError:
                    pass

    # Sort pending by analyzed_at (newest first)
    pending.sort(key=lambda x: x.get("analyzed_at", ""), reverse=True)
    completed.sort(key=lambda x: x.get("completed_at", ""), reverse=True)

    return jsonify({
        "pending": pending,
        "completed": completed,
        "processing": [],  # TODO: Phase 2 - real-time analysis tracking
    })


def validate_action_id(action_id: str) -> bool:
    """Validate action ID format to prevent injection."""
    return bool(ACTION_ID_PATTERN.match(action_id))


@app.route('/api/action/<action_id>/content')
def get_action_content(action_id: str):
    """Get full content for an action."""
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    items = scan_actionable_items()

    for item in items:
        if item["id"] == action_id:
            return jsonify({
                "id": item["id"],
                "content": item["content"],
                "raw_data": item.get("raw_data"),
                "type": item["type"],
                "destination": item["destination"],
                "source_title": item["source_title"],
                "source_decimal": item["source_decimal"],
                "word_count": item["word_count"],
                "analyzed_at": item["analyzed_at"],
                "relative_time": format_relative_time(item["analyzed_at"]),
            })

    return jsonify({"error": "Action not found"}), 404


@app.route('/api/action/<action_id>/copy', methods=['POST'])
def copy_action(action_id: str):
    """Server-side clipboard copy using pyperclip."""
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    items = scan_actionable_items()

    for item in items:
        if item["id"] == action_id:
            try:
                pyperclip.copy(item["content"])

                # Update state
                state = load_action_state()
                if action_id not in state["actions"]:
                    state["actions"][action_id] = {
                        "status": "pending",
                        "copied_count": 0,
                        "created_at": datetime.now().isoformat(),
                    }

                state["actions"][action_id]["copied_count"] += 1
                save_action_state(state)

                return jsonify({
                    "success": True,
                    "copied_count": state["actions"][action_id]["copied_count"],
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Action not found"}), 404


@app.route('/api/action/<action_id>/done', methods=['POST'])
def mark_done(action_id: str):
    """Mark action as done."""
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    state = load_action_state()

    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "done",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    else:
        state["actions"][action_id]["status"] = "done"

    state["actions"][action_id]["completed_at"] = datetime.now().isoformat()
    save_action_state(state)

    return jsonify({"success": True})


@app.route('/api/action/<action_id>/skip', methods=['POST'])
def skip_action(action_id: str):
    """Mark action as skipped."""
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    state = load_action_state()

    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "skipped",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    else:
        state["actions"][action_id]["status"] = "skipped"

    state["actions"][action_id]["completed_at"] = datetime.now().isoformat()
    save_action_state(state)

    return jsonify({"success": True})


@app.route('/api/posting-queue')
def get_posting_queue():
    """Get approved items for posting queue.

    Returns only approved items filtered to actionable types (linkedin_post, skool_post).
    Includes runway count by platform.
    """
    state = load_action_state()
    items = scan_actionable_items()

    # Filter to approved items only
    approved_items = []
    runway_counts = {}

    for item in items:
        item_state = state["actions"].get(item["id"], {})
        status = item_state.get("status", "pending")

        if status == "approved":
            # Add state info to item
            item["status"] = "approved"
            item["approved_at"] = item_state.get("approved_at", "")
            item["relative_time"] = format_relative_time(item["analyzed_at"])

            # Add visual status info
            item["visual_status"] = item_state.get("visual_status", "pending")
            visual_data = item_state.get("visual_data", {})
            item["visual_format"] = visual_data.get("format", "")

            # Build thumbnail URL if available
            thumbnail_paths = visual_data.get("thumbnail_paths", [])
            if thumbnail_paths and len(thumbnail_paths) > 0:
                # Convert absolute path to relative URL via /visuals/ route
                first_thumb = thumbnail_paths[0]
                try:
                    rel_path = str(Path(first_thumb).relative_to(KB_ROOT))
                    item["thumbnail_url"] = f"/visuals/{rel_path}"
                except ValueError:
                    item["thumbnail_url"] = None
            else:
                item["thumbnail_url"] = None

            # Build PDF URL if available
            pdf_path = visual_data.get("pdf_path", "")
            if pdf_path:
                try:
                    rel_path = str(Path(pdf_path).relative_to(KB_ROOT))
                    item["pdf_url"] = f"/visuals/{rel_path}"
                except ValueError:
                    item["pdf_url"] = None
            else:
                item["pdf_url"] = None

            approved_items.append(item)

            # Count by destination/platform
            dest = item["destination"]
            runway_counts[dest] = runway_counts.get(dest, 0) + 1

    # Sort by approved_at (newest first)
    approved_items.sort(key=lambda x: x.get("approved_at", ""), reverse=True)

    return jsonify({
        "items": approved_items,
        "runway_counts": runway_counts,
        "total": len(approved_items),
    })


@app.route('/visuals/<path:filepath>')
def serve_visual(filepath: str):
    """Serve generated visual files (PDFs, thumbnails) from KB_ROOT.

    Validates the path stays within KB_ROOT to prevent directory traversal.
    """
    # Resolve to prevent directory traversal
    full_path = (KB_ROOT / filepath).resolve()
    if not str(full_path).startswith(str(KB_ROOT.resolve())):
        return jsonify({"error": "Invalid path"}), 403

    if not full_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_from_directory(
        str(full_path.parent),
        full_path.name,
    )


@app.route('/api/action/<action_id>/approve', methods=['POST'])
def approve_action(action_id: str):
    """Mark action as approved for posting queue.

    Sets status to 'approved' and records approved_at timestamp.
    Also copies content to clipboard (auto-copy on approve).
    Requires item to be in 'pending' status (or no status yet).
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Get item content for clipboard copy
    items = scan_actionable_items()
    item_content = None
    for item in items:
        if item["id"] == action_id:
            item_content = item["content"]
            break

    if item_content is None:
        return jsonify({"error": "Action not found"}), 404

    # Update state
    state = load_action_state()

    # Validate state transition: must be pending (or not set) before approving
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status != "pending":
        return jsonify({"error": f"Cannot approve item with status '{current_status}'. Item must be pending."}), 400

    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "approved",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    else:
        state["actions"][action_id]["status"] = "approved"

    state["actions"][action_id]["approved_at"] = datetime.now().isoformat()
    save_action_state(state)

    # Auto-copy to clipboard
    try:
        pyperclip.copy(item_content)
        copied = True
    except Exception:
        copied = False

    # Trigger visual pipeline in background thread
    transcript_path = None
    for item in items:
        if item["id"] == action_id:
            transcript_path = item.get("transcript_path")
            break

    if transcript_path:
        thread = threading.Thread(
            target=run_visual_pipeline,
            args=(action_id, transcript_path),
            daemon=True,
        )
        thread.start()
        logger.info("[KB Serve] Visual pipeline started for %s", action_id)

    return jsonify({"success": True, "copied": copied})


@app.route('/api/action/<action_id>/posted', methods=['POST'])
def mark_posted(action_id: str):
    """Mark action as posted.

    Sets status to 'posted' and records posted_at timestamp.
    Requires item to be in 'approved' status first.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    state = load_action_state()

    # Validate state transition: must be approved before posting
    if action_id not in state["actions"] or state["actions"][action_id].get("status") != "approved":
        return jsonify({"error": "Item must be approved before marking as posted"}), 400

    state["actions"][action_id]["status"] = "posted"
    state["actions"][action_id]["posted_at"] = datetime.now().isoformat()
    save_action_state(state)

    return jsonify({"success": True})


@app.route('/api/action/<action_id>/flag', methods=['POST'])
def flag_action(action_id: str):
    """Flag an action for prompt quality feedback.

    Stores flag in prompt-feedback.json and marks action as skipped.
    Request body: { "note": "optional note" }
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Extract analysis_type from action_id (format: transcript_id--analysis_type)
    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return jsonify({"error": "Invalid action ID format"}), 400

    analysis_type = parts[1]

    # Get optional note from request body
    data = request.get_json() or {}
    note = data.get("note", "")

    # Add flag to prompt feedback
    feedback = load_prompt_feedback()
    feedback["flags"].append({
        "analysis_type": analysis_type,
        "action_id": action_id,
        "flagged_at": datetime.now().isoformat(),
        "note": note,
    })
    save_prompt_feedback(feedback)

    # Also mark action as skipped (reuse skip logic)
    state = load_action_state()
    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "skipped",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    else:
        state["actions"][action_id]["status"] = "skipped"

    state["actions"][action_id]["completed_at"] = datetime.now().isoformat()
    state["actions"][action_id]["flagged"] = True  # Mark as flagged for reference
    save_action_state(state)

    return jsonify({"success": True})


# --- Browse Mode Routes ---

@app.route('/browse')
def browse():
    """Browse mode HTML."""
    return render_template('browse.html')


@app.route('/api/categories')
def get_categories():
    """List decimals (categories) with transcript counts."""
    categories = []

    # Scan all decimal directories
    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue

        # Count JSON files (transcripts)
        transcript_count = sum(1 for f in decimal_dir.glob("*.json"))

        if transcript_count > 0:
            categories.append({
                "decimal": decimal_dir.name,
                "count": transcript_count,
            })

    # Sort by decimal
    categories.sort(key=lambda x: x["decimal"])

    return jsonify({"categories": categories})


@app.route('/api/transcripts/<decimal>')
def get_transcripts(decimal: str):
    """List transcripts in a category."""
    # Validate decimal format (XX.XX.XX pattern)
    if not re.match(r'^\d{2}\.\d{2}\.\d{2}$', decimal):
        return jsonify({"error": "Invalid decimal format"}), 400

    decimal_dir = KB_ROOT / decimal
    if not decimal_dir.exists():
        return jsonify({"error": "Category not found"}), 404

    transcripts = []
    for json_file in decimal_dir.glob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)

            # Get analysis types
            analysis_types = list(data.get("analysis", {}).keys())

            transcripts.append({
                "id": data.get("id", json_file.stem),
                "title": data.get("title", "Untitled"),
                "date": data.get("metadata", {}).get("transcribed_at", ""),
                "source_type": data.get("source", {}).get("type", "unknown"),
                "word_count": data.get("metadata", {}).get("word_count", 0),
                "analysis_types": analysis_types,
                "file_path": str(json_file),
            })
        except (json.JSONDecodeError, KeyError, IOError):
            continue

    # Sort by date (newest first)
    transcripts.sort(key=lambda x: x.get("date", ""), reverse=True)

    return jsonify({"transcripts": transcripts, "decimal": decimal})


@app.route('/api/transcript/<transcript_id>')
def get_transcript(transcript_id: str):
    """Get full transcript with all analyses."""
    # Validate transcript ID format
    if not re.match(r'^[\w\.\-]+$', transcript_id):
        return jsonify({"error": "Invalid transcript ID format"}), 400

    # Search for transcript by ID across all decimal directories
    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue

        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)

                if data.get("id") == transcript_id:
                    # Format analyses for display
                    analyses = []
                    for name, content in data.get("analysis", {}).items():
                        if isinstance(content, dict):
                            # Check for nested content (e.g., summary.summary)
                            inner = content.get(name)
                            analyzed_at = content.get("_analyzed_at", "")
                            model = content.get("_model", "")

                            if inner is not None:
                                if isinstance(inner, str):
                                    display_content = inner
                                else:
                                    display_content = json.dumps(inner, indent=2, ensure_ascii=False)
                            elif "post" in content:
                                # Special case for analysis types like linkedin_post with 'post' field
                                display_content = content["post"]
                            else:
                                # Filter out metadata keys for display
                                display_data = {k: v for k, v in content.items() if not k.startswith("_")}
                                display_content = json.dumps(display_data, indent=2, ensure_ascii=False)
                        else:
                            display_content = str(content)
                            analyzed_at = ""
                            model = ""

                        analyses.append({
                            "name": name,
                            "content": display_content,
                            "analyzed_at": analyzed_at,
                            "relative_time": format_relative_time(analyzed_at),
                            "model": model,
                            "word_count": len(display_content.split()) if display_content else 0,
                        })

                    return jsonify({
                        "id": data.get("id"),
                        "title": data.get("title", "Untitled"),
                        "decimal": data.get("decimal", ""),
                        "transcript": data.get("transcript", ""),
                        "transcript_word_count": data.get("metadata", {}).get("word_count", 0),
                        "source_type": data.get("source", {}).get("type", "unknown"),
                        "source_path": data.get("source", {}).get("path", ""),
                        "transcribed_at": data.get("metadata", {}).get("transcribed_at", ""),
                        "duration": data.get("metadata", {}).get("duration_seconds", 0),
                        "analyses": analyses,
                        "tags": data.get("tags", []),
                    })

            except (json.JSONDecodeError, KeyError, IOError):
                continue

    return jsonify({"error": "Transcript not found"}), 404


@app.route('/api/search')
def search_transcripts():
    """Search transcripts by query term."""
    query = request.args.get('q', '').lower().strip()
    if not query or len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400

    results = []
    limit = 50  # Limit results

    # Search across all decimal directories
    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue

        for json_file in decimal_dir.glob("*.json"):
            if len(results) >= limit:
                break

            try:
                with open(json_file) as f:
                    data = json.load(f)

                # Search in title
                title = data.get("title", "")
                title_match = query in title.lower()

                # Search in transcript
                transcript = data.get("transcript", "")
                transcript_match = query in transcript.lower()

                # Search in tags
                tags = data.get("tags", [])
                tag_match = any(query in tag.lower() for tag in tags)

                if title_match or transcript_match or tag_match:
                    # Find matching snippet if transcript match
                    snippet = ""
                    if transcript_match:
                        # Get context around match
                        idx = transcript.lower().find(query)
                        start = max(0, idx - 50)
                        end = min(len(transcript), idx + len(query) + 50)
                        snippet = "..." + transcript[start:end] + "..."

                    results.append({
                        "id": data.get("id", json_file.stem),
                        "title": title,
                        "decimal": data.get("decimal", ""),
                        "source_type": data.get("source", {}).get("type", "unknown"),
                        "match_type": "title" if title_match else ("tag" if tag_match else "transcript"),
                        "snippet": snippet,
                        "date": data.get("metadata", {}).get("transcribed_at", ""),
                    })

            except (json.JSONDecodeError, KeyError, IOError):
                continue

        if len(results) >= limit:
            break

    # Sort by date (newest first)
    results.sort(key=lambda x: x.get("date", ""), reverse=True)

    return jsonify({"results": results, "query": query, "count": len(results)})


# --- Videos Tab Routes ---

@app.route('/videos')
def videos():
    """Videos tab HTML."""
    return render_template('videos.html')


@app.route('/api/video-inventory')
def get_video_inventory():
    """Get full video inventory."""
    inventory = load_inventory()
    videos = inventory.get("videos", {})
    last_scan = inventory.get("last_scan")

    # Group by status and decimal
    by_status = {"linked": [], "unlinked": [], "processing": [], "missing": []}
    by_decimal = {}
    by_source = {}

    for video_id, video in videos.items():
        status = video.get("status", "unlinked")
        if status in by_status:
            by_status[status].append(video)

        # Group by decimal for linked videos
        if status == "linked" and video.get("transcript_id"):
            decimal = video["transcript_id"].split("-")[0]
            if decimal not in by_decimal:
                by_decimal[decimal] = []
            by_decimal[decimal].append(video)

        # Group by source label
        source = video.get("source_label", "Unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(video)

    return jsonify({
        "videos": list(videos.values()),
        "by_status": by_status,
        "by_decimal": by_decimal,
        "by_source": by_source,
        "last_scan": last_scan,
        "counts": {
            "total": len(videos),
            "linked": len(by_status["linked"]),
            "unlinked": len(by_status["unlinked"]),
            "processing": len(by_status["processing"]),
            "missing": len(by_status["missing"]),
        }
    })


@app.route('/api/video/<video_id>')
def get_video(video_id: str):
    """Get single video details."""
    if not re.match(r'^[a-f0-9]{12}\Z', video_id):
        return jsonify({"error": "Invalid video ID format"}), 400

    inventory = load_inventory()
    video = inventory.get("videos", {}).get(video_id)

    if not video:
        return jsonify({"error": "Video not found"}), 404

    # If linked, get transcript preview
    transcript_preview = None
    if video.get("status") == "linked" and video.get("transcript_id"):
        transcript_id = video["transcript_id"]
        # Find transcript file
        for decimal_dir in KB_ROOT.iterdir():
            if not decimal_dir.is_dir():
                continue
            for json_file in decimal_dir.glob("*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                    if data.get("id") == transcript_id:
                        transcript_text = data.get("transcript", "")
                        transcript_preview = transcript_text[:500] + "..." if len(transcript_text) > 500 else transcript_text
                        break
                except Exception:
                    continue
            if transcript_preview:
                break

    return jsonify({
        **video,
        "transcript_preview": transcript_preview,
    })


@app.route('/api/video/<video_id>/link', methods=['POST'])
def link_video(video_id: str):
    """Manually link video to transcript."""
    if not re.match(r'^[a-f0-9]{12}\Z', video_id):
        return jsonify({"error": "Invalid video ID format"}), 400

    data = request.get_json()
    transcript_id = data.get("transcript_id")

    if not transcript_id:
        return jsonify({"error": "transcript_id required"}), 400

    if not re.match(r'^[\w\.\-]+$', transcript_id):
        return jsonify({"error": "Invalid transcript ID format"}), 400

    inventory = load_inventory()
    if video_id not in inventory.get("videos", {}):
        return jsonify({"error": "Video not found"}), 404

    inventory["videos"][video_id]["status"] = "linked"
    inventory["videos"][video_id]["transcript_id"] = transcript_id
    inventory["videos"][video_id]["match_confidence"] = 1.0  # Manual link = full confidence
    inventory["videos"][video_id]["linked_at"] = datetime.now().isoformat()

    save_inventory(inventory)

    return jsonify({"success": True, "video": inventory["videos"][video_id]})


@app.route('/api/video/<video_id>/unlink', methods=['POST'])
def unlink_video(video_id: str):
    """Remove link between video and transcript."""
    if not re.match(r'^[a-f0-9]{12}\Z', video_id):
        return jsonify({"error": "Invalid video ID format"}), 400

    inventory = load_inventory()
    if video_id not in inventory.get("videos", {}):
        return jsonify({"error": "Video not found"}), 404

    inventory["videos"][video_id]["status"] = "unlinked"
    inventory["videos"][video_id]["transcript_id"] = None
    inventory["videos"][video_id]["match_confidence"] = None
    inventory["videos"][video_id]["linked_at"] = None

    save_inventory(inventory)

    return jsonify({"success": True, "video": inventory["videos"][video_id]})


@app.route('/api/video-rescan', methods=['POST'])
def rescan_videos():
    """Trigger a video rescan."""
    try:
        # Run quick scan (no smart matching) for speed
        result = scan_videos(quick=True, reorganize=False, yes=True, cron=True)
        return jsonify({
            "success": True,
            "result": result,
        })
    except Exception as e:
        return jsonify({"error": "Scan failed"}), 500


@app.route('/api/video/<video_id>/transcribe', methods=['POST'])
def transcribe_video(video_id: str):
    """Queue a video for transcription."""
    if not re.match(r'^[a-f0-9]{12}\Z', video_id):
        return jsonify({"error": "Invalid video ID format"}), 400

    data = request.get_json() or {}
    decimal = data.get("decimal")
    title = data.get("title")
    tags = data.get("tags", [])

    if not decimal:
        return jsonify({"error": "decimal required"}), 400

    if not title:
        return jsonify({"error": "title required"}), 400

    # Validate decimal format (XX.XX.XX pattern)
    if not re.match(r'^\d{2}\.\d{2}\.\d{2}$', decimal):
        return jsonify({"error": "Invalid decimal format (expected XX.XX.XX)"}), 400

    try:
        job = queue_transcription(
            video_id=video_id,
            decimal=decimal,
            title=title,
            tags=tags,
        )
        return jsonify({
            "success": True,
            "job": job,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Failed to queue transcription"}), 500


@app.route('/api/transcription-queue')
def get_transcription_queue():
    """Get transcription queue status."""
    status = get_queue_status()
    return jsonify(status)


@app.route('/api/decimals')
def get_decimals():
    """Get available decimal categories from registry."""
    from kb.core import load_registry
    registry = load_registry()
    decimals = registry.get("decimals", {})

    # Format for frontend
    result = [
        {"decimal": k, "label": v}
        for k, v in sorted(decimals.items())
    ]
    return jsonify({"decimals": result})


@app.route('/api/presets')
def get_presets():
    """Get available presets from config."""
    presets = _config.get("presets", {})

    # Format for frontend
    result = [
        {
            "id": k,
            "label": v.get("label", k),
            "decimal": v.get("decimal", ""),
            "tags": v.get("tags", []),
            "sources": v.get("sources", []),
        }
        for k, v in presets.items()
    ]
    return jsonify({"presets": result})


# --- Prompts Routes ---

@app.route('/prompts')
def prompts():
    """Prompts page HTML."""
    return render_template('prompts.html')


@app.route('/api/prompts')
def get_prompts():
    """Get all analysis types with flag stats.

    Returns list of prompts sorted by flag_rate descending (bubbling).
    """
    # Load prompt feedback and action state for stats
    feedback = load_prompt_feedback()
    action_state = load_action_state()

    # Count flags by analysis type
    flags_by_type = {}
    recent_flags_by_type = {}
    flagged_ids_by_type = {}
    seven_days_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)

    for flag in feedback.get("flags", []):
        analysis_type = flag.get("analysis_type", "")
        if not analysis_type:
            continue

        if analysis_type not in flags_by_type:
            flags_by_type[analysis_type] = 0
            recent_flags_by_type[analysis_type] = 0
            flagged_ids_by_type[analysis_type] = []

        flags_by_type[analysis_type] += 1
        flagged_ids_by_type[analysis_type].append(flag.get("action_id", ""))

        # Check if recent (within 7 days)
        flagged_at = flag.get("flagged_at", "")
        if flagged_at:
            try:
                flag_ts = datetime.fromisoformat(flagged_at).timestamp()
                if flag_ts > seven_days_ago:
                    recent_flags_by_type[analysis_type] += 1
            except (ValueError, TypeError):
                pass

    # Count total actions by analysis type for flag_rate calculation
    actions_by_type = {}
    for action_id in action_state.get("actions", {}).keys():
        # action_id format: transcript_id--analysis_type
        parts = action_id.split(ACTION_ID_SEP)
        if len(parts) == 2:
            analysis_type = parts[1]
            actions_by_type[analysis_type] = actions_by_type.get(analysis_type, 0) + 1

    # Build response for each analysis type
    prompts_list = []
    for analysis_type in list_analysis_types():
        name = analysis_type["name"]

        try:
            full_def = load_analysis_type(name)
        except ValueError:
            continue

        # Calculate stats
        total_flagged = flags_by_type.get(name, 0)
        total_actions = actions_by_type.get(name, 0)
        flag_rate = total_flagged / total_actions if total_actions > 0 else 0.0

        prompts_list.append({
            "name": name,
            "description": analysis_type.get("description", ""),
            "prompt_preview": full_def.get("prompt", "")[:200] + "..." if len(full_def.get("prompt", "")) > 200 else full_def.get("prompt", ""),
            "prompt_full": full_def.get("prompt", ""),
            "output_schema": full_def.get("output_schema", {}),
            "file_path": str(ANALYSIS_TYPES_DIR / f"{name}.json"),
            "stats": {
                "total_flagged": total_flagged,
                "flag_rate": round(flag_rate, 3),
                "recent_flags": recent_flags_by_type.get(name, 0),
                "total_actions": total_actions,
                "flagged_action_ids": flagged_ids_by_type.get(name, []),
            }
        })

    # Sort by flag_rate descending (bubbling mechanism)
    prompts_list.sort(key=lambda x: x["stats"]["flag_rate"], reverse=True)

    return jsonify({"prompts": prompts_list})


def check_and_auto_scan():
    """Check if inventory is stale and run auto-scan if needed."""
    inventory = load_inventory()
    last_scan = inventory.get("last_scan")

    if not last_scan:
        # Never scanned - run initial scan
        print("[KB Serve] No video inventory found, running initial scan...")
        scan_videos(quick=True, reorganize=False, yes=True, cron=True)
        return

    try:
        last_scan_dt = datetime.fromisoformat(last_scan)
        age_hours = (datetime.now() - last_scan_dt).total_seconds() / 3600

        if age_hours > 1:
            print(f"[KB Serve] Video inventory is {age_hours:.1f}h old, running auto-scan...")
            scan_videos(quick=True, reorganize=False, yes=True, cron=True)
    except (ValueError, TypeError):
        pass


# --- CLI Entry Point ---

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="KB Serve - Action Queue Dashboard")
    parser.add_argument("--port", type=int, default=8765, help="Port to run on (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")

    args = parser.parse_args()

    print(f"[KB Serve] Starting action queue dashboard on http://{args.host}:{args.port}")
    print(f"[KB Serve] KB Root: {KB_ROOT}")
    print(f"[KB Serve] Action State: {ACTION_STATE_PATH}")
    print(f"[KB Serve] Video Inventory: {INVENTORY_PATH}")
    print(f"[KB Serve] Press Ctrl+C to stop")

    # Auto-scan videos if inventory is stale (>1hr)
    check_and_auto_scan()

    try:
        app.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n[KB Serve] Shutting down cleanly...")


if __name__ == "__main__":
    main()
