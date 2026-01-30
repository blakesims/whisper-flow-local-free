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
import re
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import Flask, render_template, jsonify, request
import pyperclip

# Action ID separator (using -- to avoid URL encoding issues with ::)
ACTION_ID_SEP = "--"
# Regex for validating action IDs: transcript_id--analysis_name
ACTION_ID_PATTERN = re.compile(r'^[\w\.\-]+--[a-z_]+$')

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.__main__ import load_config, get_paths

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
ACTION_STATE_PATH = Path.home() / ".kb" / "action-state.json"

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
        elif item_state["status"] in ("done", "skipped"):
            item["completed_at"] = item_state["completed_at"]

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
    print(f"[KB Serve] Press Ctrl+C to stop")

    try:
        app.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n[KB Serve] Shutting down cleanly...")


if __name__ == "__main__":
    main()
