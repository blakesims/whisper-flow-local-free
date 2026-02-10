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
import argparse
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
import pyperclip

from kb.videos import (
    load_inventory, save_inventory, scan_videos, INVENTORY_PATH,
    queue_transcription, get_queue_status, start_worker, load_queue
)
from kb.analyze import list_analysis_types, load_analysis_type, ANALYSIS_TYPES_DIR, AUTO_JUDGE_TYPES, run_with_judge_loop

logger = logging.getLogger(__name__)

from kb.serve_scanner import (
    ACTION_ID_SEP, ACTION_ID_PATTERN, VERSIONED_KEY_PATTERN,
    get_action_mapping, get_destination_for_action,
    scan_actionable_items, get_action_status,
    format_relative_time, validate_action_id,
)

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.config import load_config, get_paths

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
ACTION_STATE_PATH = Path.home() / ".kb" / "action-state.json"
PROMPT_FEEDBACK_PATH = Path.home() / ".kb" / "prompt-feedback.json"

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))


# --- Action State Management ---

from kb.serve_state import (
    load_action_state,
    save_action_state,
    load_prompt_feedback,
    save_prompt_feedback,
)


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


# --- Visual Pipeline (Background Thread) ---

from kb.serve_visual import (
    _update_visual_status,
    _find_transcript_file,
    run_visual_pipeline,
)


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

    # Trigger visual pipeline in background thread — but NOT for auto-judge types
    # (linkedin_v2 items go through the iteration workflow: iterate -> stage -> generate visuals)
    parts = action_id.split(ACTION_ID_SEP)
    analysis_type = parts[1] if len(parts) == 2 else ""

    if analysis_type not in AUTO_JUDGE_TYPES:
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


@app.route('/api/action/<action_id>/stage', methods=['POST'])
def stage_action(action_id: str):
    """Stage an iteration for the curation workflow.

    Sets status to 'staged'. Does NOT trigger visual pipeline.
    Used by 'a' shortcut in iteration view for linkedin_v2 items.
    Requires item to be in 'pending' or 'draft' status.

    Also creates the initial edit version (linkedin_v2_N_0) in the transcript JSON,
    where N is the current round number of the staged iteration.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Get item content for clipboard copy
    items = scan_actionable_items()
    item_content = None
    transcript_path = None
    for item in items:
        if item["id"] == action_id:
            item_content = item["content"]
            transcript_path = item.get("transcript_path")
            break

    if item_content is None:
        return jsonify({"error": "Action not found"}), 404

    # Update state
    state = load_action_state()

    # Validate state transition: must be pending or draft
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status not in ("pending", "draft"):
        return jsonify({"error": f"Cannot stage item with status '{current_status}'. Item must be pending or draft."}), 400

    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "staged",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    else:
        state["actions"][action_id]["status"] = "staged"

    state["actions"][action_id]["staged_at"] = datetime.now().isoformat()

    # Create initial edit version (_N_0) for auto-judge types
    parts = action_id.split(ACTION_ID_SEP)
    analysis_type = parts[1] if len(parts) == 2 else ""
    edit_round = 0
    edit_number = 0

    if analysis_type in AUTO_JUDGE_TYPES and transcript_path:
        try:
            with open(transcript_path) as f:
                transcript_data = json.load(f)

            alias = transcript_data.get("analysis", {}).get(analysis_type, {})
            current_round = alias.get("_round", 0)
            edit_round = current_round

            # Create _N_0 edit version (the raw LLM output snapshot)
            edit_key = f"{analysis_type}_{current_round}_0"
            if edit_key not in transcript_data.get("analysis", {}):
                transcript_data["analysis"][edit_key] = {
                    "post": alias.get("post", ""),
                    "_edited_at": datetime.now().isoformat(),
                    "_source": f"{analysis_type}_{current_round}",
                }
                # Update alias _edit metadata
                alias["_edit"] = 0
                with open(transcript_path, 'w') as f:
                    json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning("[KB Serve] Failed to create edit version on stage: %s", e)

    state["actions"][action_id]["staged_round"] = edit_round
    state["actions"][action_id]["edit_count"] = edit_number
    save_action_state(state)

    # Auto-copy to clipboard
    try:
        pyperclip.copy(item_content)
        copied = True
    except Exception:
        copied = False

    return jsonify({"success": True, "copied": copied, "staged_round": edit_round})


@app.route('/api/action/<action_id>/save-edit', methods=['POST'])
def save_edit(action_id: str):
    """Save a text edit, creating a new edit version.

    Creates linkedin_v2_N_M+1 where N is the staged round and M is the current
    edit number. Updates the linkedin_v2 alias to point to the latest edit.

    Request body: { "text": "edited post text" }
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return jsonify({"error": "Invalid action ID format"}), 400

    analysis_type = parts[1]

    # Must be staged to save edits
    state = load_action_state()
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status not in ("staged", "ready"):
        return jsonify({"error": f"Cannot edit item with status '{current_status}'. Item must be staged or ready."}), 400

    # Get the edited text from request body
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Request body must contain 'text' field"}), 400

    edited_text = data["text"]

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    try:
        with open(str(transcript_path)) as f:
            transcript_data = json.load(f)

        alias = transcript_data.get("analysis", {}).get(analysis_type, {})
        current_round = alias.get("_round", 0)
        current_edit = alias.get("_edit", 0)

        # Determine the staged round from action state
        staged_round = state["actions"].get(action_id, {}).get("staged_round", current_round)

        # Next edit number
        next_edit = current_edit + 1
        edit_key = f"{analysis_type}_{staged_round}_{next_edit}"
        source_key = f"{analysis_type}_{staged_round}_{current_edit}"

        # Save the new edit version
        transcript_data["analysis"][edit_key] = {
            "post": edited_text,
            "_edited_at": datetime.now().isoformat(),
            "_source": source_key,
        }

        # Update alias to point to latest edit
        alias["post"] = edited_text
        alias["_edit"] = next_edit
        alias["_edited_at"] = datetime.now().isoformat()

        with open(str(transcript_path), 'w') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        # Update edit count in action state
        state["actions"][action_id]["edit_count"] = next_edit

        # Invalidate stale visuals: if item is "ready", reset to "staged"
        # so user must re-render after editing (Phase 3 code review fix)
        if current_status == "ready":
            state["actions"][action_id]["status"] = "staged"
            state["actions"][action_id]["visual_status"] = "stale"
            logger.info("[KB Serve] Visual status invalidated for %s after edit", action_id)

        save_action_state(state)

        return jsonify({
            "success": True,
            "edit_key": edit_key,
            "edit_number": next_edit,
        })

    except (json.JSONDecodeError, IOError) as e:
        logger.error("[KB Serve] Failed to save edit: %s", e)
        return jsonify({"error": "Failed to save edit"}), 500


@app.route('/api/action/<action_id>/generate-visuals', methods=['POST'])
def generate_visuals(action_id: str):
    """Trigger visual pipeline from staging.

    Runs run_visual_pipeline() in a background thread.
    Only allowed when item is in 'staged' status.
    Updates visual_status to 'generating' immediately.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Must be staged to generate visuals
    state = load_action_state()
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status != "staged":
        return jsonify({"error": f"Cannot generate visuals for item with status '{current_status}'. Item must be staged."}), 400

    # Check not already generating
    visual_status = state["actions"].get(action_id, {}).get("visual_status", "")
    if visual_status == "generating":
        return jsonify({"error": "Visual generation already in progress"}), 400

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    # Get template from request if provided
    data = request.get_json() or {}
    template_name = data.get("template")

    # Start visual pipeline in background thread
    def _run_and_update_status():
        run_visual_pipeline(action_id, str(transcript_path), template_name=template_name)
        # After visuals complete, update status to "ready" if visual_status is "ready"
        st = load_action_state()
        if action_id in st["actions"]:
            vs = st["actions"][action_id].get("visual_status", "")
            if vs in ("ready", "text_only"):
                st["actions"][action_id]["status"] = "ready"
                save_action_state(st)

    thread = threading.Thread(target=_run_and_update_status, daemon=True)
    thread.start()
    logger.info("[KB Serve] Visual pipeline started from staging for %s", action_id)

    return jsonify({"success": True, "message": "Visual generation started"})


@app.route('/api/templates')
def get_templates():
    """List available carousel templates.

    Reads template names and descriptions from carousel_templates/config.json.
    Returns list of templates with the current default marked.
    """
    try:
        from kb.render import load_carousel_config
        config = load_carousel_config()
    except (FileNotFoundError, ImportError) as e:
        return jsonify({"error": f"Could not load carousel config: {e}"}), 500

    templates_config = config.get("templates", {})
    default_template = config.get("defaults", {}).get("template", "brand-purple")

    templates = []
    for name, tpl in templates_config.items():
        templates.append({
            "name": name,
            "description": tpl.get("description", ""),
            "file": tpl.get("file", ""),
            "is_default": name == default_template,
        })

    return jsonify({
        "templates": templates,
        "default": default_template,
    })


@app.route('/api/action/<action_id>/slides')
def get_slides(action_id: str):
    """Return carousel slide data from transcript JSON.

    Returns the carousel_slides analysis data for editing.
    Each slide has type, content, slide_number, etc.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    try:
        with open(str(transcript_path)) as f:
            transcript_data = json.load(f)

        analysis = transcript_data.get("analysis", {})
        carousel_slides = analysis.get("carousel_slides")

        if not carousel_slides:
            return jsonify({"error": "No carousel_slides data found"}), 404

        # Extract slides data -- handle nested output format
        slides_output = carousel_slides.get("output", carousel_slides)
        if isinstance(slides_output, str):
            try:
                slides_output = json.loads(slides_output)
            except (json.JSONDecodeError, TypeError):
                return jsonify({"error": "carousel_slides output not parseable"}), 500

        if not isinstance(slides_output, dict) or "slides" not in slides_output:
            if "slides" in carousel_slides:
                slides_output = {
                    "slides": carousel_slides["slides"],
                    "total_slides": carousel_slides.get("total_slides", len(carousel_slides["slides"])),
                    "has_mermaid": carousel_slides.get("has_mermaid", False),
                }
            else:
                return jsonify({"error": "No slides data in carousel_slides"}), 404

        slides = slides_output.get("slides", [])

        return jsonify({
            "action_id": action_id,
            "slides": slides,
            "total_slides": len(slides),
            "has_mermaid": slides_output.get("has_mermaid", False),
        })

    except (json.JSONDecodeError, IOError) as e:
        logger.error("[KB Serve] Failed to load slides: %s", e)
        return jsonify({"error": "Failed to load slides"}), 500


@app.route('/api/action/<action_id>/save-slides', methods=['POST'])
def save_slides(action_id: str):
    """Save edited slide data back to transcript JSON.

    Updates the carousel_slides analysis data with edited slide content.
    Slide types are read-only; only title and content fields are updated.
    Also invalidates visual_status to "stale" since slides changed.

    Request body: { "slides": [ { slide_number, type, title, content, ... } ] }
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Must be staged or ready to save slide edits
    state = load_action_state()
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status not in ("staged", "ready"):
        return jsonify({"error": f"Cannot edit slides with status '{current_status}'. Item must be staged or ready."}), 400

    data = request.get_json()
    if not data or "slides" not in data:
        return jsonify({"error": "Request body must contain 'slides' field"}), 400

    edited_slides = data["slides"]
    if not isinstance(edited_slides, list):
        return jsonify({"error": "'slides' must be a list"}), 400

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    try:
        with open(str(transcript_path)) as f:
            transcript_data = json.load(f)

        analysis = transcript_data.get("analysis", {})
        carousel_slides = analysis.get("carousel_slides", {})

        # Get existing slides data
        slides_output = carousel_slides.get("output", carousel_slides)
        if isinstance(slides_output, str):
            try:
                slides_output = json.loads(slides_output)
            except (json.JSONDecodeError, TypeError):
                return jsonify({"error": "carousel_slides output not parseable"}), 500

        if not isinstance(slides_output, dict):
            slides_output = {}

        existing_slides = slides_output.get("slides", carousel_slides.get("slides", []))

        # Validate incoming fields
        valid_formats = ("bullets", "numbered", "paragraph")
        for edited in edited_slides:
            if "format" in edited and edited["format"] not in valid_formats:
                return jsonify({"error": f"Invalid format '{edited['format']}'. Must be one of: {', '.join(valid_formats)}"}), 400
            if "bullets" in edited and edited["bullets"] is not None:
                if not isinstance(edited["bullets"], list) or not all(isinstance(b, str) for b in edited["bullets"]):
                    return jsonify({"error": "'bullets' must be a list of strings"}), 400
            if "subtitle" in edited and not isinstance(edited["subtitle"], str):
                return jsonify({"error": "'subtitle' must be a string"}), 400

        # Update existing slides with edits (preserving type)
        for edited in edited_slides:
            slide_num = edited.get("slide_number")
            if slide_num is None:
                continue

            # Find matching existing slide
            for existing in existing_slides:
                if existing.get("slide_number") == slide_num:
                    # Update title
                    if "title" in edited:
                        existing["title"] = edited["title"]

                    # Update subtitle (hook/CTA slides)
                    if "subtitle" in edited:
                        existing["subtitle"] = edited["subtitle"]

                    # Update format
                    if "format" in edited:
                        existing["format"] = edited["format"]

                    # Update content based on format
                    if "bullets" in edited and edited["bullets"] is not None:
                        existing["bullets"] = edited["bullets"]
                        # Set content as fallback string
                        existing["content"] = ". ".join(edited["bullets"])
                    elif "format" in edited and edited["format"] == "paragraph":
                        # Paragraph format: clear bullets, write content
                        existing.pop("bullets", None)
                        if "content" in edited:
                            existing["content"] = edited["content"]
                    elif "content" in edited:
                        existing["content"] = edited["content"]
                    break

        # Save back to transcript
        if "output" in carousel_slides and isinstance(carousel_slides["output"], dict):
            carousel_slides["output"]["slides"] = existing_slides
        elif "output" in carousel_slides and isinstance(carousel_slides["output"], str):
            # Was a string, now make it a dict
            carousel_slides["output"] = {
                "slides": existing_slides,
                "total_slides": len(existing_slides),
                "has_mermaid": slides_output.get("has_mermaid", False),
            }
        else:
            carousel_slides["slides"] = existing_slides

        carousel_slides["_slides_edited_at"] = datetime.now().isoformat()
        analysis["carousel_slides"] = carousel_slides

        with open(str(transcript_path), 'w') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        # Invalidate visuals since slides changed
        if current_status == "ready":
            state["actions"][action_id]["status"] = "staged"
        state["actions"][action_id]["visual_status"] = "stale"
        save_action_state(state)
        logger.info("[KB Serve] Slides saved and visual status invalidated for %s", action_id)

        return jsonify({
            "success": True,
            "slides_count": len(existing_slides),
        })

    except (json.JSONDecodeError, IOError) as e:
        logger.error("[KB Serve] Failed to save slides: %s", e)
        return jsonify({"error": "Failed to save slides"}), 500


@app.route('/api/action/<action_id>/render', methods=['POST'])
def render_action(action_id: str):
    """Re-render carousel with specified template.

    Triggers a re-render of the carousel using the current slide data
    and the specified template name. Runs in background thread.

    Request body: { "template": "brand-purple" } (optional, defaults to config default)
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    # Must be staged or ready
    state = load_action_state()
    current_status = state["actions"].get(action_id, {}).get("status", "pending")
    if current_status not in ("staged", "ready"):
        return jsonify({"error": f"Cannot render for item with status '{current_status}'. Item must be staged or ready."}), 400

    # Check not already generating
    visual_status = state["actions"].get(action_id, {}).get("visual_status", "")
    if visual_status == "generating":
        return jsonify({"error": "Render already in progress"}), 400

    # Get template name from request
    data = request.get_json() or {}
    template_name = data.get("template")

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    # Start render in background thread
    def _run_render():
        try:
            _update_visual_status(action_id, "generating")

            with open(str(transcript_path)) as f:
                transcript_data = json.load(f)

            analysis = transcript_data.get("analysis", {})
            carousel_slides = analysis.get("carousel_slides", {})

            # Extract slides data
            slides_output = carousel_slides.get("output", carousel_slides)
            if isinstance(slides_output, str):
                try:
                    slides_output = json.loads(slides_output)
                except (json.JSONDecodeError, TypeError):
                    _update_visual_status(action_id, "failed", {"error": "carousel_slides output not parseable"})
                    return

            if not isinstance(slides_output, dict) or "slides" not in slides_output:
                if "slides" in carousel_slides:
                    slides_output = {
                        "slides": carousel_slides["slides"],
                        "total_slides": carousel_slides.get("total_slides", len(carousel_slides["slides"])),
                        "has_mermaid": carousel_slides.get("has_mermaid", False),
                    }
                else:
                    _update_visual_status(action_id, "failed", {"error": "No slides data"})
                    return

            # Build output dir
            decimal_dir = Path(str(transcript_path)).parent
            visuals_dir = decimal_dir / "visuals"

            from kb.render import render_pipeline
            result = render_pipeline(slides_output, str(visuals_dir), template_name=template_name)

            if result.get("pdf_path"):
                visual_data = {
                    "format": "CAROUSEL",
                    "pdf_path": result["pdf_path"],
                    "thumbnail_paths": result.get("thumbnail_paths", []),
                    "errors": result.get("errors", []),
                    "template": template_name or "default",
                }
                _update_visual_status(action_id, "ready", visual_data)

                # Update action status to ready
                st = load_action_state()
                if action_id in st["actions"]:
                    st["actions"][action_id]["status"] = "ready"
                    save_action_state(st)

                logger.info("[KB Serve] Re-render complete for %s", action_id)
            else:
                _update_visual_status(action_id, "failed", {
                    "error": "Render produced no PDF",
                    "errors": result.get("errors", []),
                })

        except Exception as e:
            logger.error("[KB Serve] Render failed for %s: %s", action_id, e)
            _update_visual_status(action_id, "failed", {"error": str(e)})

    thread = threading.Thread(target=_run_render, daemon=True)
    thread.start()
    logger.info("[KB Serve] Re-render started for %s (template=%s)", action_id, template_name or "default")

    return jsonify({"success": True, "message": "Render started", "template": template_name or "default"})


@app.route('/api/action/<action_id>/edit-history')
def get_edit_history(action_id: str):
    """Return edit versions for a staged item.

    Returns all edit sub-versions (linkedin_v2_N_0, _N_1, etc.)
    for the staged round.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return jsonify({"error": "Invalid action ID format"}), 400

    analysis_type = parts[1]

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    try:
        with open(str(transcript_path)) as f:
            transcript_data = json.load(f)

        analysis = transcript_data.get("analysis", {})
        alias = analysis.get(analysis_type, {})

        # Determine the staged round from action state
        state = load_action_state()
        staged_round = state["actions"].get(action_id, {}).get("staged_round", alias.get("_round", 0))

        # Collect edit versions for this round
        edits = []
        edit_num = 0
        while True:
            edit_key = f"{analysis_type}_{staged_round}_{edit_num}"
            if edit_key not in analysis:
                break
            edit_data = analysis[edit_key]
            edits.append({
                "edit_number": edit_num,
                "key": edit_key,
                "post": edit_data.get("post", ""),
                "edited_at": edit_data.get("_edited_at", ""),
                "source": edit_data.get("_source", ""),
            })
            edit_num += 1

        current_edit = alias.get("_edit", 0)

        return jsonify({
            "action_id": action_id,
            "staged_round": staged_round,
            "current_edit": current_edit,
            "edits": edits,
            "total_edits": len(edits),
        })

    except (json.JSONDecodeError, IOError) as e:
        logger.error("[KB Serve] Failed to load edit history: %s", e)
        return jsonify({"error": "Failed to load edit history"}), 500


@app.route('/api/action/<action_id>/iterate', methods=['POST'])
def iterate_action(action_id: str):
    """Trigger next improvement round in background thread.

    Calls run_with_judge_loop() for the next iteration.
    Returns immediately; client polls /iterations for updates.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return jsonify({"error": "Invalid action ID format"}), 400

    analysis_type = parts[1]
    if analysis_type not in AUTO_JUDGE_TYPES:
        return jsonify({"error": f"Analysis type '{analysis_type}' does not support iteration"}), 400

    judge_type = AUTO_JUDGE_TYPES[analysis_type]

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    # Update state to show iterating
    state = load_action_state()
    if action_id not in state["actions"]:
        state["actions"][action_id] = {
            "status": "pending",
            "copied_count": 0,
            "created_at": datetime.now().isoformat(),
        }
    state["actions"][action_id]["iterating"] = True
    save_action_state(state)

    def _run_iteration():
        try:
            with open(str(transcript_path)) as f:
                transcript_data = json.load(f)

            existing_analysis = transcript_data.get("analysis", {})

            run_with_judge_loop(
                transcript_data=transcript_data,
                analysis_type=analysis_type,
                judge_type=judge_type,
                max_rounds=1,
                existing_analysis=existing_analysis,
                save_path=str(transcript_path),
            )
        except Exception as e:
            logger.error("[KB Serve] Iteration failed for %s: %s", action_id, e)
        finally:
            # Clear iterating flag
            st = load_action_state()
            if action_id in st["actions"]:
                st["actions"][action_id]["iterating"] = False
                save_action_state(st)

    thread = threading.Thread(target=_run_iteration, daemon=True)
    thread.start()
    logger.info("[KB Serve] Iteration started for %s", action_id)

    return jsonify({"success": True, "message": "Iteration started"})


@app.route('/api/action/<action_id>/iterations')
def get_iterations(action_id: str):
    """Return all iterations with scores for an entity.

    Returns versioned drafts and judge scores for display in iteration view.
    Uses alias-based action_id (e.g., transcript_id--linkedin_v2).
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    parts = action_id.split(ACTION_ID_SEP)
    if len(parts) != 2:
        return jsonify({"error": "Invalid action ID format"}), 400

    transcript_id = parts[0]
    analysis_type = parts[1]

    if analysis_type not in AUTO_JUDGE_TYPES:
        return jsonify({"error": f"Analysis type '{analysis_type}' does not support iterations"}), 400

    judge_type = AUTO_JUDGE_TYPES[analysis_type]

    # Find transcript file
    transcript_path = _find_transcript_file(action_id)
    if not transcript_path:
        return jsonify({"error": "Transcript file not found"}), 404

    with open(str(transcript_path)) as f:
        transcript_data = json.load(f)

    analysis = transcript_data.get("analysis", {})
    alias = analysis.get(analysis_type, {})

    # Build iterations list
    iterations = []
    round_num = 0
    while True:
        draft_key = f"{analysis_type}_{round_num}"
        judge_key = f"{judge_type}_{round_num}"

        if draft_key not in analysis:
            break

        draft_data = analysis[draft_key]
        judge_data = analysis.get(judge_key)

        iteration = {
            "round": round_num,
            "post": draft_data.get("post", ""),
            "model": draft_data.get("_model", ""),
            "analyzed_at": draft_data.get("_analyzed_at", ""),
            "scores": None,
        }

        if judge_data and isinstance(judge_data, dict):
            iteration["scores"] = {
                "overall": judge_data.get("overall_score", 0),
                "criteria": judge_data.get("scores", {}),
                "improvements": judge_data.get("improvements", []),
                "rewritten_hook": judge_data.get("rewritten_hook"),
            }

        iterations.append(iteration)
        round_num += 1

    # If no versioned keys but alias exists (pre-T023 content), show alias as round 0
    if not iterations and alias:
        iteration = {
            "round": 0,
            "post": alias.get("post", ""),
            "model": alias.get("_model", ""),
            "analyzed_at": alias.get("_analyzed_at", ""),
            "scores": None,
        }
        # Check for unversioned judge
        judge_data = analysis.get(judge_type)
        if judge_data and isinstance(judge_data, dict):
            iteration["scores"] = {
                "overall": judge_data.get("overall_score", 0),
                "criteria": judge_data.get("scores", {}),
                "improvements": judge_data.get("improvements", []),
                "rewritten_hook": judge_data.get("rewritten_hook"),
            }
        iterations.append(iteration)

    # Get iterating status from action state
    state = load_action_state()
    iterating = state.get("actions", {}).get(action_id, {}).get("iterating", False)

    # Current round from alias
    current_round = alias.get("_round", 0) if alias else 0
    score_history = alias.get("_history", {}).get("scores", []) if alias else []

    return jsonify({
        "action_id": action_id,
        "iterations": iterations,
        "current_round": current_round,
        "score_history": score_history,
        "iterating": iterating,
        "total_rounds": len(iterations),
    })


@app.route('/api/posting-queue-v2')
def get_posting_queue_v2():
    """Get items for the iteration view posting queue.

    Returns items grouped as entities (not individual iterations).
    Includes iteration counts and latest scores for each entity.
    Draft, pending, staged, and ready items for linkedin_v2 types.
    """
    state = load_action_state()
    items = scan_actionable_items()

    entities = []

    for item in items:
        item_state = state["actions"].get(item["id"], {})
        status = item_state.get("status", "pending")

        # Include pending, draft, staged, and ready items
        if status in ("pending", "draft", "staged", "ready"):
            # Load iteration data for auto-judge types
            parts = item["id"].split(ACTION_ID_SEP)
            analysis_type = parts[1] if len(parts) == 2 else ""

            iteration_count = 0
            latest_score = None
            score_history = []
            iterating = item_state.get("iterating", False)

            if analysis_type in AUTO_JUDGE_TYPES:
                # Parse iteration info from raw_data (alias metadata)
                raw = item.get("raw_data", {}) or {}
                current_round = 0

                # Try to get _round and _history from the transcript file
                transcript_path = item.get("transcript_path")
                if transcript_path:
                    try:
                        with open(transcript_path) as f:
                            tdata = json.load(f)
                        alias = tdata.get("analysis", {}).get(analysis_type, {})
                        current_round = alias.get("_round", 0)
                        score_history = alias.get("_history", {}).get("scores", [])
                        iteration_count = current_round + 1  # 0-indexed rounds

                        if score_history:
                            latest = score_history[-1]
                            latest_score = latest.get("overall", 0)
                    except (json.JSONDecodeError, IOError, KeyError):
                        pass

            item["status"] = status
            item["iteration_count"] = iteration_count
            item["latest_score"] = latest_score
            item["score_history"] = score_history
            item["iterating"] = iterating
            item["relative_time"] = format_relative_time(item["analyzed_at"])

            # Staging metadata
            item["visual_status"] = item_state.get("visual_status", "")
            item["staged_round"] = item_state.get("staged_round", 0)
            item["edit_count"] = item_state.get("edit_count", 0)

            # Visual data for thumbnails
            visual_data = item_state.get("visual_data", {})
            thumbnail_paths = visual_data.get("thumbnail_paths", [])
            if thumbnail_paths:
                try:
                    rel_path = str(Path(thumbnail_paths[0]).relative_to(KB_ROOT))
                    item["thumbnail_url"] = f"/visuals/{rel_path}"
                except (ValueError, IndexError):
                    item["thumbnail_url"] = None
            else:
                item["thumbnail_url"] = None

            entities.append(item)

    # Sort: iterating first, then staged/ready before draft, then by latest_score descending
    status_priority = {"ready": 0, "staged": 1, "pending": 2, "draft": 3}
    entities.sort(key=lambda x: (
        not x.get("iterating", False),
        status_priority.get(x.get("status", "pending"), 9),
        -(x.get("latest_score") or 0),
        x.get("analyzed_at", ""),
    ), reverse=False)

    return jsonify({
        "items": entities,
        "total": len(entities),
    })


@app.route('/api/action/<action_id>/posted', methods=['POST'])
def mark_posted(action_id: str):
    """Mark action as posted.

    Sets status to 'posted' and records posted_at timestamp.
    Requires item to be in 'approved' or 'ready' status first.
    """
    if not validate_action_id(action_id):
        return jsonify({"error": "Invalid action ID format"}), 400

    state = load_action_state()

    # Validate state transition: must be approved or ready before posting
    current_status = state["actions"].get(action_id, {}).get("status", "")
    if current_status not in ("approved", "ready"):
        return jsonify({"error": "Item must be approved or ready before marking as posted"}), 400

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
