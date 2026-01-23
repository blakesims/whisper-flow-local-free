"""
KB Sources - Modular source handlers for transcription.

Each source handles a specific type of input (file, cap recording, volume, etc.)
and produces transcript JSON files in the knowledge base.
"""

from typing import Callable

# Source registry - maps source key to handler info
SOURCES = {
    "file": {
        "label": "File",
        "description": "Transcribe a single audio/video file",
        "handler": "kb.sources.file",
    },
    "cap": {
        "label": "Cap",
        "description": "Batch process Cap recordings",
        "handler": "kb.sources.cap",
    },
    "volume": {
        "label": "Volume",
        "description": "Auto-transcribe from mounted volume",
        "handler": "kb.sources.volume",
    },
    "zoom": {
        "label": "Zoom",
        "description": "Transcribe Zoom meeting recordings",
        "handler": "kb.sources.zoom",
    },
    "paste": {
        "label": "Paste",
        "description": "Import transcript from clipboard",
        "handler": "kb.sources.paste",
    },
}


def get_source_choices() -> list[tuple[str, str, str]]:
    """
    Get list of source choices for menu display.

    Returns list of (key, label, description) tuples.
    """
    choices = []
    for key, info in SOURCES.items():
        # Skip placeholder sources
        if info.get("placeholder"):
            continue
        choices.append((key, info["label"], info["description"]))
    return choices


def run_source(source_key: str, args: list[str], interactive: bool = False):
    """
    Run a specific source handler.

    Args:
        source_key: Key from SOURCES dict
        args: Command line arguments to pass to source
        interactive: Whether running in interactive mode
    """
    import importlib
    import sys

    if source_key not in SOURCES:
        raise ValueError(f"Unknown source: {source_key}")

    source_info = SOURCES[source_key]

    if source_info.get("placeholder"):
        from rich.console import Console
        Console().print(f"[yellow]{source_info['label']} source not yet implemented.[/yellow]")
        return

    # Import and run the source module
    module = importlib.import_module(source_info["handler"])

    # Set sys.argv for the source
    sys.argv = [source_key] + args

    # Call main() or run_interactive() based on mode
    if interactive and hasattr(module, "run_interactive"):
        module.run_interactive()
    else:
        module.main()
