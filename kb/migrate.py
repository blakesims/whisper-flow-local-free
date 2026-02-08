"""
KB Migrate - One-time data migrations for KB workflow changes.

Usage:
    kb migrate                    # Show available migrations
    kb migrate --reset-approved   # Reset approved items to draft (T023)
"""

import argparse
import sys

from rich.console import Console

console = Console()


def main():
    """Main entry point for kb migrate."""
    parser = argparse.ArgumentParser(
        description="KB Migrate - Run data migrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--reset-approved",
        action="store_true",
        help="Reset all approved items to draft state (T023 migration)",
    )

    args = parser.parse_args()

    if not args.reset_approved:
        parser.print_help()
        console.print("\n[dim]Available migrations:[/dim]")
        console.print("  --reset-approved  Reset approved items to draft (T023)")
        return

    if args.reset_approved:
        from kb.serve import migrate_approved_to_draft
        count = migrate_approved_to_draft()
        if count > 0:
            console.print(f"[green]Migrated {count} approved item(s) to draft state.[/green]")
        else:
            console.print("[dim]No approved items to migrate.[/dim]")


if __name__ == "__main__":
    main()
