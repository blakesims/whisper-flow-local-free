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
            "linkedin_post": "LinkedIn",
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
            "path": "/Volumes/BackupArchive/skool-videos",
            "label": "Skool Videos",
        },
        {
            "path": "/Volumes/BackupArchive/cap-exports",
            "label": "Cap Exports",
        },
    ],
    "video_target": "/Volumes/BackupArchive/kb-videos",
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
    "clean": {
        "label": "Clean",
        "description": "Clean up Cap recording by removing junk segments",
        "module": "kb.sources.cap_clean",
    },
    "analyze": {
        "label": "Analyze",
        "description": "Run LLM analysis on existing transcript",
        "module": "kb.analyze",
    },
    "serve": {
        "label": "Serve",
        "description": "Start action queue dashboard web server",
        "module": "kb.serve",
    },
    "process-inbox": {
        "label": "Process Inbox",
        "description": "Process files dropped in inbox directories",
        "module": "kb.inbox",
    },
    "dashboard": {
        "label": "Dashboard",
        "description": "Open visual overview of KB configuration in browser",
        "module": "kb.dashboard",
    },
    "scan-videos": {
        "label": "Scan Videos",
        "description": "Scan video sources and link to transcripts",
        "module": "kb.videos",
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

    # Presets section
    console.print("\n[bold cyan]Presets[/bold cyan]  [dim](quick input for common workflows)[/dim]")
    presets = config.get("presets", {})
    if presets:
        # Group by source
        by_source = {}
        for key, preset in presets.items():
            for source in preset.get("sources", ["all"]):
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append((key, preset))

        for source in sorted(by_source.keys()):
            source_presets = by_source[source]
            preset_names = [f"[green]{preset.get('label', key)}[/green] ({preset.get('decimal', '')})"
                          for key, preset in source_presets]
            console.print(f"  [cyan]{source}:[/cyan] {', '.join(preset_names)}")
    else:
        console.print("  [yellow]No presets configured[/yellow]")

    # Zoom ignore list
    zoom_config = config.get("zoom", {})
    ignore_list = zoom_config.get("ignore_participants", [])
    if ignore_list:
        console.print(f"\n[bold cyan]Zoom Ignore List[/bold cyan]")
        console.print(f"  {', '.join(ignore_list)}")

    # Analysis types section
    console.print("\n[bold cyan]Analysis Prompts[/bold cyan]  [dim](config/analysis_types/)[/dim]")
    if analysis_types:
        console.print(f"  {len(analysis_types)} types: [green]{', '.join(sorted(analysis_types))}[/green]")
    else:
        console.print("  [yellow]No analysis types configured[/yellow]")

    # Config submenu
    console.print()

    editor = os.environ.get("EDITOR", "nvim")
    editor_name = os.path.basename(editor)

    while True:
        edit_choice = questionary.select(
            "",
            choices=[
                questionary.Choice(title="← Back to menu", value="back"),
                questionary.Choice(title=f"Edit config in {editor_name}", value="edit"),
                questionary.Choice(title="Manage decimals", value="decimals"),
                questionary.Choice(title="View analysis types", value="analysis"),
            ],
            style=custom_style,
            instruction="(↑/↓ navigate, Enter select)",
        ).ask()

        if edit_choice == "back" or edit_choice is None:
            return

        if edit_choice == "decimals":
            manage_decimals()
            continue

        if edit_choice == "analysis":
            view_analysis_types()
            continue

        if edit_choice == "edit":
            import subprocess
            config_path = CONFIG_FILE.resolve() if CONFIG_FILE.is_symlink() else CONFIG_FILE

            # Ensure config file exists with starter template
            if not config_path.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w') as f:
                    f.write("""# KB Workflow Configuration
# See defaults in kb/__main__.py

# Uncomment and modify to customize:
# presets:
#   my_preset:
#     label: "My Custom Preset"
#     decimal: "50.01.01"
#     title_template: "{filename}"
#     tags: ["my-tag"]
#     sources: ["file", "cap"]

# zoom:
#   ignore_participants:
#     - "Fireflies"
#     - "Otter"
""")

            console.print(f"[dim]Opening {shorten_path(config_path)}...[/dim]")
            subprocess.run([editor, str(config_path)])
            return


def manage_decimals():
    """Interactive decimal category management."""
    import json
    from kb.core import load_registry

    registry = load_registry()
    decimals = registry.get("decimals", {})

    console.print(Panel("[bold]Manage Decimal Categories[/bold]", border_style="cyan"))

    if not decimals:
        console.print("\n[yellow]No decimal categories defined yet.[/yellow]")
        console.print("[dim]Add your first decimal to get started.[/dim]\n")
    else:
        # Display existing decimals as a table
        console.print("\n[bold cyan]Existing Decimals[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Decimal", style="cyan")
        table.add_column("Name")
        table.add_column("Description", style="dim", max_width=40)
        table.add_column("Default Analyses", style="green")

        for decimal_code in sorted(decimals.keys()):
            info = decimals[decimal_code]
            name = info.get("name", "") if isinstance(info, dict) else info
            description = info.get("description", "") if isinstance(info, dict) else ""
            analyses = info.get("default_analyses", []) if isinstance(info, dict) else []

            # Truncate description if too long
            if len(description) > 40:
                description = description[:37] + "..."

            analyses_str = ", ".join(analyses) if analyses else "[dim]none[/dim]"

            table.add_row(decimal_code, name, description, analyses_str)

        console.print(table)
        console.print()

    # Submenu for decimal management
    action = questionary.select(
        "",
        choices=[
            questionary.Choice(title="← Back", value="back"),
            questionary.Choice(title="Add new decimal", value="add"),
            questionary.Choice(title="Edit existing decimal", value="edit"),
        ],
        style=custom_style,
        instruction="(↑/↓ navigate, Enter select)",
    ).ask()

    if action == "back" or action is None:
        return

    if action == "add":
        add_decimal()
        return

    if action == "edit":
        edit_decimal()
        return


def add_decimal():
    """Interactive flow to add a new decimal category."""
    import re
    import json
    from kb.core import load_registry, save_registry
    from kb.analyze import list_analysis_types

    console.print(Panel("[bold]Add New Decimal Category[/bold]", border_style="cyan"))

    registry = load_registry()
    decimals = registry.get("decimals", {})

    # Get available analysis types for multi-select
    analysis_types = list_analysis_types()
    analysis_choices = [
        questionary.Choice(
            title=f"{t['name']}: {t['description'][:50]}{'...' if len(t['description']) > 50 else ''}",
            value=t["name"],
            checked=False
        )
        for t in analysis_types
    ]

    # Validation function for decimal format
    def validate_decimal(text: str) -> bool | str:
        if not text:
            return "Decimal code is required"
        if not re.match(r'^\d+(\.\d+)*$', text):
            return "Invalid format. Use digits separated by dots (e.g., 50.01.01)"
        if text in decimals:
            return f"Decimal '{text}' already exists"
        return True

    # Prompt for decimal code
    console.print("\n[dim]Format: digits separated by dots (e.g., 50.01.01, 60.02)[/dim]\n")

    decimal_code = questionary.text(
        "Decimal code:",
        validate=validate_decimal,
        style=custom_style,
    ).ask()

    if not decimal_code:
        console.print("[dim]Cancelled[/dim]")
        return

    # Prompt for name
    name = questionary.text(
        "Name:",
        validate=lambda x: True if x.strip() else "Name is required",
        style=custom_style,
    ).ask()

    if not name:
        console.print("[dim]Cancelled[/dim]")
        return

    name = name.strip()

    # Prompt for description (optional)
    description = questionary.text(
        "Description (optional):",
        default="",
        style=custom_style,
    ).ask()

    if description is None:
        console.print("[dim]Cancelled[/dim]")
        return

    description = description.strip()

    # Prompt for default analyses (multi-select)
    console.print("\n[dim]Select default analyses to run on new transcripts:[/dim]")

    if analysis_choices:
        default_analyses = questionary.checkbox(
            "Default analyses:",
            choices=analysis_choices,
            style=custom_style,
            instruction="(space to select, enter to confirm)",
        ).ask()

        if default_analyses is None:
            console.print("[dim]Cancelled[/dim]")
            return
    else:
        console.print("[yellow]No analysis types available yet.[/yellow]")
        default_analyses = []

    # Show summary and confirm
    console.print("\n[bold cyan]Summary[/bold cyan]")
    console.print(f"  Decimal: [cyan]{decimal_code}[/cyan]")
    console.print(f"  Name: {name}")
    if description:
        console.print(f"  Description: [dim]{description}[/dim]")
    if default_analyses:
        console.print(f"  Default analyses: [green]{', '.join(default_analyses)}[/green]")
    else:
        console.print("  Default analyses: [dim]none[/dim]")

    confirm = questionary.confirm(
        "\nSave this decimal?",
        default=True,
        style=custom_style,
    ).ask()

    if not confirm:
        console.print("[dim]Cancelled[/dim]")
        return

    # Save to registry
    if "decimals" not in registry:
        registry["decimals"] = {}

    registry["decimals"][decimal_code] = {
        "name": name,
        "description": description,
        "default_analyses": default_analyses,
    }

    if save_registry(registry):
        console.print(f"\n[green]✓ Decimal '{decimal_code}' added successfully![/green]\n")
    else:
        console.print(f"\n[red]✗ Failed to save decimal. Check file permissions.[/red]\n")


def edit_decimal():
    """Interactive flow to edit an existing decimal category."""
    import json
    from kb.core import load_registry, save_registry
    from kb.analyze import list_analysis_types

    registry = load_registry()
    decimals = registry.get("decimals", {})

    if not decimals:
        console.print("\n[yellow]No decimal categories to edit.[/yellow]")
        console.print("[dim]Add a decimal first.[/dim]\n")
        return

    console.print(Panel("[bold]Edit Decimal Category[/bold]", border_style="cyan"))

    # Build choices for decimal selection
    decimal_choices = [
        questionary.Choice(
            title=f"{code}: {info.get('name', info) if isinstance(info, dict) else info}",
            value=code
        )
        for code, info in sorted(decimals.items())
    ]
    decimal_choices.insert(0, questionary.Choice(title="← Cancel", value=None))

    # Select decimal to edit
    decimal_code = questionary.select(
        "Select decimal to edit:",
        choices=decimal_choices,
        style=custom_style,
    ).ask()

    if not decimal_code:
        return

    # Get current values
    current = decimals[decimal_code]
    if isinstance(current, str):
        # Legacy format: just a name string
        current = {"name": current, "description": "", "default_analyses": []}

    current_name = current.get("name", "")
    current_description = current.get("description", "")
    current_analyses = current.get("default_analyses", [])

    # Show current values
    console.print(f"\n[bold cyan]Current Values[/bold cyan]")
    console.print(f"  Decimal: [cyan]{decimal_code}[/cyan]")
    console.print(f"  Name: {current_name}")
    console.print(f"  Description: [dim]{current_description or '(none)'}[/dim]")
    console.print(f"  Default analyses: [green]{', '.join(current_analyses) if current_analyses else '(none)'}[/green]")

    # Submenu for what to edit
    edit_action = questionary.select(
        "\nWhat would you like to do?",
        choices=[
            questionary.Choice(title="← Cancel", value="cancel"),
            questionary.Choice(title="Edit name", value="name"),
            questionary.Choice(title="Edit description", value="description"),
            questionary.Choice(title="Edit default analyses", value="analyses"),
            questionary.Choice(title="Edit all fields", value="all"),
            questionary.Choice(title="Delete this decimal", value="delete"),
        ],
        style=custom_style,
    ).ask()

    if edit_action == "cancel" or edit_action is None:
        return

    if edit_action == "delete":
        delete_decimal(decimal_code, registry)
        return

    # Get available analysis types for multi-select
    analysis_types = list_analysis_types()
    analysis_choices = [
        questionary.Choice(
            title=f"{t['name']}: {t['description'][:50]}{'...' if len(t['description']) > 50 else ''}",
            value=t["name"],
            checked=(t["name"] in current_analyses)
        )
        for t in analysis_types
    ]

    new_name = current_name
    new_description = current_description
    new_analyses = current_analyses

    # Edit based on selection
    if edit_action in ("name", "all"):
        result = questionary.text(
            "Name:",
            default=current_name,
            validate=lambda x: True if x.strip() else "Name is required",
            style=custom_style,
        ).ask()
        if result is None:
            console.print("[dim]Cancelled[/dim]")
            return
        new_name = result.strip()

    if edit_action in ("description", "all"):
        result = questionary.text(
            "Description:",
            default=current_description,
            style=custom_style,
        ).ask()
        if result is None:
            console.print("[dim]Cancelled[/dim]")
            return
        new_description = result.strip()

    if edit_action in ("analyses", "all"):
        if analysis_choices:
            result = questionary.checkbox(
                "Default analyses:",
                choices=analysis_choices,
                style=custom_style,
                instruction="(space to select, enter to confirm)",
            ).ask()
            if result is None:
                console.print("[dim]Cancelled[/dim]")
                return
            new_analyses = result
        else:
            console.print("[yellow]No analysis types available.[/yellow]")

    # Check if anything changed
    changed = (new_name != current_name or
               new_description != current_description or
               set(new_analyses) != set(current_analyses))

    if not changed:
        console.print("\n[dim]No changes made.[/dim]\n")
        return

    # Show summary of changes
    console.print("\n[bold cyan]Changes[/bold cyan]")
    if new_name != current_name:
        console.print(f"  Name: [dim]{current_name}[/dim] → [green]{new_name}[/green]")
    if new_description != current_description:
        old_desc = current_description or "(none)"
        new_desc = new_description or "(none)"
        console.print(f"  Description: [dim]{old_desc}[/dim] → [green]{new_desc}[/green]")
    if set(new_analyses) != set(current_analyses):
        old_analyses = ", ".join(current_analyses) if current_analyses else "(none)"
        new_analyses_str = ", ".join(new_analyses) if new_analyses else "(none)"
        console.print(f"  Analyses: [dim]{old_analyses}[/dim] → [green]{new_analyses_str}[/green]")

    confirm = questionary.confirm(
        "\nSave changes?",
        default=True,
        style=custom_style,
    ).ask()

    if not confirm:
        console.print("[dim]Cancelled[/dim]")
        return

    # Save to registry
    registry["decimals"][decimal_code] = {
        "name": new_name,
        "description": new_description,
        "default_analyses": new_analyses,
    }

    if save_registry(registry):
        console.print(f"\n[green]✓ Decimal '{decimal_code}' updated successfully![/green]\n")
    else:
        console.print(f"\n[red]✗ Failed to save changes. Check file permissions.[/red]\n")


def delete_decimal(decimal_code: str, registry: dict):
    """Delete a decimal category with safety checks."""
    from kb.core import save_registry

    # Check if any transcripts use this decimal
    # We could scan the transcripts directory, but for now we'll just warn
    console.print(f"\n[yellow]Warning:[/yellow] Deleting decimal [cyan]{decimal_code}[/cyan]")
    console.print("[dim]Existing transcripts using this decimal will not be affected,[/dim]")
    console.print("[dim]but new transcripts won't be able to use it.[/dim]\n")

    confirm = questionary.confirm(
        f"Delete decimal '{decimal_code}'?",
        default=False,
        style=custom_style,
    ).ask()

    if not confirm:
        console.print("[dim]Cancelled[/dim]")
        return

    # Double confirm for safety
    confirm2 = questionary.text(
        f"Type '{decimal_code}' to confirm deletion:",
        style=custom_style,
    ).ask()

    if confirm2 != decimal_code:
        console.print("[dim]Cancelled (confirmation did not match)[/dim]")
        return

    # Delete from registry
    del registry["decimals"][decimal_code]
    if save_registry(registry):
        console.print(f"\n[green]✓ Decimal '{decimal_code}' deleted.[/green]\n")
    else:
        console.print(f"\n[red]✗ Failed to delete. Check file permissions.[/red]\n")


def view_analysis_types():
    """Display available analysis types from config directory."""
    import json

    paths = get_paths(load_config())
    analysis_dir = paths["config_dir"] / "analysis_types"

    console.print(Panel("[bold]Available Analysis Types[/bold]", border_style="cyan"))

    if not analysis_dir.exists():
        console.print(f"\n[yellow]Analysis types directory not found:[/yellow]")
        console.print(f"[dim]{shorten_path(analysis_dir)}/[/dim]\n")
        console.print("[dim]Create JSON files in this directory to define analysis types.[/dim]\n")
        return

    analysis_files = list(analysis_dir.glob("*.json"))
    if not analysis_files:
        console.print(f"\n[yellow]No analysis types defined yet.[/yellow]")
        console.print(f"[dim]Add .json files to: {shorten_path(analysis_dir)}/[/dim]\n")
        return

    # Build table of analysis types
    console.print("\n")
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Output Type", style="dim")

    for analysis_file in sorted(analysis_files):
        try:
            with open(analysis_file) as f:
                data = json.load(f)

            name = data.get("name", analysis_file.stem)
            description = data.get("description", "")

            # Determine output type from schema
            schema = data.get("output_schema", {})
            props = schema.get("properties", {})
            if props:
                first_key = list(props.keys())[0]
                first_prop = props[first_key]
                output_type = first_prop.get("type", "unknown")
                if output_type == "object":
                    output_type = "structured"
            else:
                output_type = "text"

            table.add_row(name, description, output_type)

        except (json.JSONDecodeError, IOError) as e:
            table.add_row(
                analysis_file.stem,
                f"[red]Error loading: {e}[/red]",
                ""
            )

    console.print(table)
    console.print(f"\n[dim]Location: {shorten_path(analysis_dir)}/[/dim]\n")


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

    # Direct access flags for config features
    if args and args[0] in ("--decimals", "--manage-decimals"):
        manage_decimals()
        return

    if args and args[0] in ("--analysis-types", "--analyses"):
        view_analysis_types()
        return

    if args and args[0] == "--config":
        show_config()
        return

    # If args provided but not a known command, show help
    if args and args[0] not in ["--help", "-h"]:
        console.print(f"[red]Unknown command: {args[0]}[/red]\n")
        console.print("Available commands: " + ", ".join(COMMANDS.keys()))
        console.print("Direct access: --decimals, --analysis-types, --config")
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
