"""Scanner and action mapping for the KB serve dashboard.

Handles scanning KB_ROOT for actionable items, action ID validation,
and mapping analysis types to destinations.
"""
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from kb.analyze import AUTO_JUDGE_TYPES

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


def get_action_mapping(config=None) -> dict:
    """Load action mapping from config with pattern support.

    Supports three pattern types:
    - Plain: "skool_post" matches any input type
    - Typed: "meeting.student_guide" matches only meeting input type
    - Wildcard: "*.summary" matches all input types

    Returns dict mapping (input_type, analysis_type) tuples to destination labels.

    Args:
        config: Config dict. If None, lazy-imports from kb.serve.
    """
    if config is None:
        from kb.serve import _config
        config = _config

    serve_config = config.get("serve", {})
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


def scan_actionable_items(kb_root=None) -> list[dict]:
    """
    Scan all transcript JSON files in KB_ROOT for actionable analyses.

    Returns list of action items with metadata.

    Args:
        kb_root: Path to KB root directory. If None, lazy-imports from kb.serve.
    """
    if kb_root is None:
        from kb.serve import KB_ROOT
        kb_root = KB_ROOT

    action_mapping = get_action_mapping()
    action_items = []

    # Scan all decimal directories
    for decimal_dir in kb_root.iterdir():
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
        "status": action_state.get("status", "new"),
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


def validate_action_id(action_id: str) -> bool:
    """Validate action ID format to prevent injection."""
    return bool(ACTION_ID_PATTERN.match(action_id))
