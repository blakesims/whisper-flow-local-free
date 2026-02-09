# Note: kb/config/ directory (sibling) contains analysis_types JSON data files -- it is NOT this Python module.
"""
KB Configuration Module

Loads config from ~/.config/kb/config.yaml with DEFAULTS fallback.
Provides cached config access and path expansion utilities.
"""

import os
import warnings
from pathlib import Path


# Config file location
CONFIG_FILE = Path.home() / ".config" / "kb" / "config.yaml"

# Default values (used if config file missing)
DEFAULTS = {
    "paths": {
        "kb_output": "~/Obsidian/zen-ai/knowledge-base/transcripts",
        "volume_sync": "/Volumes/BackupArchive/skool-videos",
        "cap_app": "so.cap.desktop.dev",
    },
    "defaults": {
        "whisper_model": "medium",
        "gemini_model": "gemini-3-pro-preview",
        "decimal": "50.01.01",
    },
    "zoom": {
        "ignore_participants": [
            "Fireflies",
            "Otter",
            "Fathom",
        ],
    },
    "serve": {
        "action_mapping": {
            # Compound outputs
            "skool_post": "Skool",
            "skool_weekly_catchup": "Skool",
            "linkedin_v2": "LinkedIn",
            # Existing analysis types
            "summary": "Review",
            "guide": "Student",
            "lead_magnet": "Marketing",
        },
    },
    "inbox": {
        "path": "~/.kb/inbox",
        "archive_path": "~/.kb/archive",  # Set to null to delete after processing
        "decimal_defaults": {
            # Example configurations (user can override in config.yaml):
            # "50.01.01": {"analyses": ["summary", "key_points", "skool_post"]},
            # "50.03.01": {"analyses": ["summary", "key_points", "guide"]},
        },
    },
    "video_sources": [
        {
            "path": "/Volumes/SharedFiles/kb-videos/skool-videos",
            "label": "Skool Videos",
        },
        {
            "path": "/Volumes/SharedFiles/kb-videos/cap-exports",
            "label": "Cap Exports",
        },
    ],
    "video_target": "/Volumes/SharedFiles/kb-videos",
    # Remote mount mappings for SSH-based audio extraction
    # Maps local mount paths to SSH destinations for efficient extraction
    "remote_mounts": {
        "/Volumes/SharedFiles": {
            "host": "zen",  # SSH host (from ~/.ssh/config)
            "path": "/mnt/shared_storage",  # Fast USB 3.0 drive
        },
        # Keep old mapping for any legacy paths
        "/Volumes/BackupArchive": {
            "host": "zen",
            "path": "/mnt/seagate_archive",
        },
    },
    "presets": {
        "alpha_session": {
            "label": "Alpha Cohort Session",
            "decimal": "50.03.01",
            "title_template": "Alpha - {participants}",
            "tags": ["alpha-cohort", "coaching"],
            "sources": ["zoom"],
        },
        "beta_session": {
            "label": "Beta Cohort Session",
            "decimal": "50.03.02",
            "title_template": "Beta - {participants}",
            "tags": ["beta-cohort", "coaching"],
            "sources": ["zoom"],
        },
        "generic_meeting": {
            "label": "Generic Meeting",
            "decimal": "50.04",
            "title_template": "Meeting - {participants} - {date}",
            "tags": ["meeting"],
            "sources": ["zoom"],
        },
        "quick_capture": {
            "label": "Quick Capture",
            "decimal": "50.00.01",
            "title_template": "{filename}",
            "tags": [],
            "sources": ["cap", "paste"],
        },
        "skool_content": {
            "label": "Skool Classroom Content",
            "decimal": "50.01.01",
            "title_template": "{filename}",
            "tags": ["skool"],
            "sources": ["file", "volume"],
        },
    }
}


_cached_config: dict | None = None


def load_config() -> dict:
    """Load config from YAML file, falling back to defaults.

    Cached after first call -- all callers receive the same dict object.
    The returned dict should not be mutated; call _reset_config_cache()
    + load_config() if fresh config is needed.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config = DEFAULTS.copy()

    if CONFIG_FILE.exists():
        try:
            import yaml
            with open(CONFIG_FILE) as f:
                file_config = yaml.safe_load(f) or {}

            # Merge with defaults
            if "paths" in file_config:
                config["paths"] = {**DEFAULTS["paths"], **file_config["paths"]}
            if "defaults" in file_config:
                config["defaults"] = {**DEFAULTS["defaults"], **file_config["defaults"]}
            if "zoom" in file_config:
                config["zoom"] = {**DEFAULTS["zoom"], **file_config["zoom"]}
            if "serve" in file_config:
                config["serve"] = {**DEFAULTS["serve"], **file_config["serve"]}
                # Deep merge action_mapping to allow partial overrides
                if "action_mapping" in file_config["serve"]:
                    config["serve"]["action_mapping"] = {
                        **DEFAULTS["serve"]["action_mapping"],
                        **file_config["serve"]["action_mapping"]
                    }
            if "inbox" in file_config:
                config["inbox"] = {**DEFAULTS["inbox"], **file_config["inbox"]}
                # Deep merge decimal_defaults
                if "decimal_defaults" in file_config["inbox"]:
                    config["inbox"]["decimal_defaults"] = {
                        **DEFAULTS["inbox"]["decimal_defaults"],
                        **file_config["inbox"]["decimal_defaults"]
                    }
            if "presets" in file_config:
                # Deep merge presets - user can override or add new presets
                config["presets"] = {**DEFAULTS["presets"], **file_config["presets"]}
            if "video_sources" in file_config:
                config["video_sources"] = file_config["video_sources"]
            if "video_target" in file_config:
                config["video_target"] = file_config["video_target"]
            if "remote_mounts" in file_config:
                config["remote_mounts"] = {**DEFAULTS.get("remote_mounts", {}), **file_config["remote_mounts"]}
        except Exception as e:
            warnings.warn(f"Could not load config: {e}")

    _cached_config = config
    return config


def _reset_config_cache():
    """Reset cached config. Only for testing."""
    global _cached_config
    _cached_config = None


def expand_path(path_str: str) -> Path:
    """Expand ~ and return Path object."""
    return Path(os.path.expanduser(path_str))


def get_paths(config: dict) -> dict:
    """Get expanded paths from config."""
    paths = config.get("paths", DEFAULTS["paths"])

    kb_output = expand_path(paths.get("kb_output", DEFAULTS["paths"]["kb_output"]))
    cap_app = paths.get("cap_app", DEFAULTS["paths"]["cap_app"])

    return {
        "kb_output": kb_output,
        "config_dir": kb_output / "config",
        "volume_sync": Path(paths.get("volume_sync", DEFAULTS["paths"]["volume_sync"])),
        "cap_app": cap_app,
        "cap_recordings": Path.home() / "Library" / "Application Support" / cap_app / "recordings",
    }


# Load config at module level for use by other modules
_config = load_config()
_paths = get_paths(_config)

# Export for other modules
KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
VOLUME_SYNC_PATH = _paths["volume_sync"]
CAP_RECORDINGS_DIR = _paths["cap_recordings"]
