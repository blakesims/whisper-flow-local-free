"""State persistence for the KB serve dashboard.

Handles loading/saving of action state and prompt feedback JSON files.
"""
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def migrate_to_t028_statuses(path=None) -> int:
    """Migrate action-state.json to T028 lifecycle statuses.

    Idempotent: safe to run multiple times. Only modifies entries
    with old status values.

    Migrations:
        pending  -> new
        approved -> staged (preserves approved_at as staged_at)
        draft    -> new
        posted   -> done (preserves posted_at)
        skipped  -> skip

    Returns:
        Number of items migrated.
    """
    state = load_action_state(path=path)
    migrated = 0
    for action_id, data in state.get("actions", {}).items():
        status = data.get("status", "")
        if status == "pending":
            data["status"] = "new"
            migrated += 1
        elif status == "approved":
            data["status"] = "staged"
            data["staged_at"] = data.get("approved_at", datetime.now().isoformat())
            migrated += 1
        elif status == "draft":
            data["status"] = "new"
            migrated += 1
        elif status == "posted":
            data["status"] = "done"
            # posted_at already preserved in the entry
            migrated += 1
        elif status == "skipped":
            data["status"] = "skip"
            migrated += 1
    if migrated > 0:
        save_action_state(state, path=path)
        logger.info("T028 migration: migrated %d items to new statuses", migrated)
    return migrated


def load_action_state(path=None) -> dict:
    """Load action state from ~/.kb/action-state.json.

    If the file is corrupted, backs it up and returns empty state.

    Args:
        path: Path to action state file. If None, uses kb.serve.ACTION_STATE_PATH.
    """
    if path is None:
        from kb.serve import ACTION_STATE_PATH
        path = ACTION_STATE_PATH

    if not path.exists():
        return {"actions": {}}

    try:
        with open(path) as f:
            state = json.load(f)

        # Validate structure
        if not isinstance(state, dict) or "actions" not in state:
            raise ValueError("Invalid state structure")

        return state
    except (json.JSONDecodeError, IOError, ValueError) as e:
        # Backup corrupted file before resetting
        if path.exists():
            backup_path = path.with_suffix('.backup')
            shutil.copy(path, backup_path)
            print(f"[KB Serve] Warning: Corrupted action state file, backup saved to {backup_path}")

        return {"actions": {}}


def save_action_state(state: dict, path=None):
    """Save action state to ~/.kb/action-state.json.

    Args:
        path: Path to action state file. If None, uses kb.serve.ACTION_STATE_PATH.
    """
    if path is None:
        from kb.serve import ACTION_STATE_PATH
        path = ACTION_STATE_PATH

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)


def load_prompt_feedback(path=None) -> dict:
    """Load prompt feedback from ~/.kb/prompt-feedback.json.

    Returns dict with 'flags' list. Creates empty structure if file doesn't exist.

    Args:
        path: Path to prompt feedback file. If None, uses kb.serve.PROMPT_FEEDBACK_PATH.
    """
    if path is None:
        from kb.serve import PROMPT_FEEDBACK_PATH
        path = PROMPT_FEEDBACK_PATH

    if not path.exists():
        return {"flags": []}

    try:
        with open(path) as f:
            feedback = json.load(f)

        # Validate structure
        if not isinstance(feedback, dict) or "flags" not in feedback:
            return {"flags": []}

        return feedback
    except (json.JSONDecodeError, IOError):
        return {"flags": []}


def save_prompt_feedback(feedback: dict, path=None):
    """Save prompt feedback to ~/.kb/prompt-feedback.json.

    Args:
        path: Path to prompt feedback file. If None, uses kb.serve.PROMPT_FEEDBACK_PATH.
    """
    if path is None:
        from kb.serve import PROMPT_FEEDBACK_PATH
        path = PROMPT_FEEDBACK_PATH

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(feedback, f, indent=2)
