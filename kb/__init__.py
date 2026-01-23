"""
Knowledge Base Module

Tools for transcribing, analyzing, and managing transcripts in the knowledge base.

Usage:
    # Import from the package
    from kb import transcribe_to_kb, run_interactive_cli, analyze_transcript_file

    # Or run via CLI
    kb                              # Interactive main menu
    kb transcribe                   # Source submenu (file, cap, volume, paste, zoom)
    kb transcribe file <path>       # Transcribe single file
    kb transcribe cap --list        # List Cap recordings
    kb transcribe volume --dry-run  # Volume sync dry run
    kb analyze --list-types         # List analysis types
"""


def __getattr__(name):
    """Lazy import to avoid circular import issues when running modules directly."""
    if name in ("transcribe_to_kb", "load_registry", "save_registry"):
        from kb.core import transcribe_to_kb, load_registry, save_registry
        return {"transcribe_to_kb": transcribe_to_kb, "load_registry": load_registry, "save_registry": save_registry}[name]

    if name in ("run_interactive_cli", "custom_style"):
        from kb.cli import run_interactive_cli, custom_style
        return {"run_interactive_cli": run_interactive_cli, "custom_style": custom_style}[name]

    if name in ("analyze_transcript", "analyze_transcript_file", "list_analysis_types"):
        from kb.analyze import analyze_transcript, analyze_transcript_file, list_analysis_types
        return {"analyze_transcript": analyze_transcript, "analyze_transcript_file": analyze_transcript_file, "list_analysis_types": list_analysis_types}[name]

    raise AttributeError(f"module 'kb' has no attribute '{name}'")


__all__ = [
    "transcribe_to_kb",
    "load_registry",
    "save_registry",
    "run_interactive_cli",
    "custom_style",
    "analyze_transcript",
    "analyze_transcript_file",
    "list_analysis_types",
]
