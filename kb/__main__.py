#!/usr/bin/env python3
"""
KB - Knowledge Base CLI

Interactive menu for KB workflow tools.
Run with: kb (or python -m kb)
"""

import sys
import os
from pathlib import Path
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from questionary import Style

console = Console()

custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
])

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
        "gemini_model": "gemini-2.0-flash",
        "decimal": "50.01.01",
    }
}


def load_config() -> dict:
    """Load config from YAML file, falling back to defaults."""
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
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load config: {e}[/yellow]")

    return config


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

COMMANDS = {
    "transcribe": {
        "label": "Transcribe",
        "description": "Transcribe audio/video to Knowledge Base (file, cap, volume, paste)",
        "module": "kb.transcribe",
    },
    "analyze": {
        "label": "Analyze",
        "description": "Run LLM analysis on existing transcript",
        "module": "kb.analyze",
    },
}


def shorten_path(path: Path) -> str:
    """Shorten path for display, using ~ for home."""
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def show_config():
    """Display current configuration."""
    import json

    config = load_config()
    paths = get_paths(config)

    console.print(Panel("[bold]KB Configuration[/bold]", border_style="cyan"))

    # Config file status
    console.print("\n[bold cyan]Config File[/bold cyan]")
    if CONFIG_FILE.exists():
        # Check if it's a symlink
        if CONFIG_FILE.is_symlink():
            target = CONFIG_FILE.resolve()
            console.print(f"  {shorten_path(CONFIG_FILE)} [dim]→[/dim] {shorten_path(target)}  [green]linked[/green]")
        else:
            console.print(f"  {shorten_path(CONFIG_FILE)}  [green]exists[/green]")
    else:
        console.print(f"  {shorten_path(CONFIG_FILE)}  [yellow]not found (using defaults)[/yellow]")

    # Paths section
    console.print("\n[bold cyan]Paths[/bold cyan]")

    paths_table = Table(show_header=False, box=None, padding=(0, 2))
    paths_table.add_column("Label", style="dim")
    paths_table.add_column("Path")
    paths_table.add_column("Status", justify="right")

    paths_table.add_row(
        "KB Output",
        shorten_path(paths["kb_output"]),
        "[green]exists[/green]" if paths["kb_output"].exists() else "[red]missing[/red]"
    )
    paths_table.add_row(
        "Volume Sync",
        str(paths["volume_sync"]),
        "[green]mounted[/green]" if paths["volume_sync"].exists() else "[dim]not mounted[/dim]"
    )
    paths_table.add_row(
        "Cap App",
        paths["cap_app"],
        "[green]exists[/green]" if paths["cap_recordings"].exists() else "[dim]not found[/dim]"
    )
    console.print(paths_table)

    # Defaults section
    console.print("\n[bold cyan]Defaults[/bold cyan]")
    defaults = config.get("defaults", DEFAULTS["defaults"])
    defaults_table = Table(show_header=False, box=None, padding=(0, 2))
    defaults_table.add_column("Label", style="dim")
    defaults_table.add_column("Value")
    defaults_table.add_row("Whisper Model", defaults.get("whisper_model", "medium"))
    defaults_table.add_row("Gemini Model", defaults.get("gemini_model", "gemini-2.0-flash"))
    defaults_table.add_row("Decimal", defaults.get("decimal", "50.01.01"))
    console.print(defaults_table)

    # Load registry for counts
    registry = {}
    registry_path = paths["config_dir"] / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)

    # Count analysis types
    analysis_dir = paths["config_dir"] / "analysis_types"
    analysis_types = []
    if analysis_dir.exists():
        analysis_types = [f.stem for f in analysis_dir.glob("*.json")]

    # Registry section
    console.print("\n[bold cyan]Registry[/bold cyan]  [dim](config/registry.json)[/dim]")

    decimals = registry.get("decimals", {})
    tags = registry.get("tags", [])
    transcribed = registry.get("transcribed_files", [])

    reg_table = Table(show_header=False, box=None, padding=(0, 2))
    reg_table.add_column("Label", style="dim")
    reg_table.add_column("Value")

    reg_table.add_row("Categories", f"{len(decimals)} decimal codes")
    reg_table.add_row("Tags", f"{len(tags)} available")
    reg_table.add_row("Transcribed", f"{len(transcribed)} files logged")
    console.print(reg_table)

    # Analysis types section
    console.print("\n[bold cyan]Analysis Prompts[/bold cyan]  [dim](config/analysis_types/)[/dim]")
    if analysis_types:
        console.print(f"  {len(analysis_types)} types: [green]{', '.join(sorted(analysis_types))}[/green]")
    else:
        console.print("  [yellow]No analysis types configured[/yellow]")

    console.print()
    input("[dim]Press Enter to return...[/dim]")


def prompt_for_file() -> str | None:
    """Prompt user for file path interactively."""
    console.print(Panel("[bold]Transcribe to Knowledge Base[/bold]", border_style="cyan"))

    console.print("\n[dim]Enter file path, drag & drop, or paste:[/dim]")

    file_path = questionary.text(
        "File:",
        style=custom_style,
    ).ask()

    if not file_path:
        return None

    # Clean up path (remove quotes, trailing spaces)
    file_path = file_path.strip().strip("'\"")

    # Expand ~ if present
    file_path = os.path.expanduser(file_path)

    # Validate
    if not Path(file_path).exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return None

    return file_path


def show_menu() -> str | None:
    """Show interactive menu and return selected command."""
    console.print(Panel(
        "[bold]Knowledge Base Workflow[/bold]\n\n"
        "Select a command to run:",
        border_style="cyan"
    ))

    choices = [
        questionary.Choice(
            title=f"{cmd['label']:12} - {cmd['description']}",
            value=key
        )
        for key, cmd in COMMANDS.items()
    ]
    choices.append(questionary.Choice(title="Config       - View paths and settings", value="config"))
    choices.append(questionary.Choice(title="Exit", value=None))

    return questionary.select(
        "",
        choices=choices,
        style=custom_style,
        instruction="(up/down to move, Enter to select)"
    ).ask()


def run_command(command: str, args: list[str], interactive: bool = False):
    """Run the selected command's main function."""
    import importlib

    cmd_info = COMMANDS[command]
    module = importlib.import_module(cmd_info["module"])

    # Replace sys.argv so the subcommand sees correct args
    sys.argv = [command] + args
    module.main()


def main():
    """Main entry point."""
    args = sys.argv[1:]

    # If a subcommand is provided directly, run it
    if args and args[0] in COMMANDS:
        run_command(args[0], args[1:], interactive=False)
        return

    # If args provided but not a known command, show help
    if args and args[0] not in ["--help", "-h"]:
        console.print(f"[red]Unknown command: {args[0]}[/red]\n")
        console.print("Available commands: " + ", ".join(COMMANDS.keys()))
        console.print("Run [bold]kb[/bold] without arguments for interactive menu.")
        sys.exit(1)

    # Interactive menu loop
    while True:
        selected = show_menu()

        if selected is None:
            console.print("[dim]Bye![/dim]")
            return

        if selected == "config":
            show_config()
            continue

        console.print()
        run_command(selected, [], interactive=True)
        return


if __name__ == "__main__":
    main()
