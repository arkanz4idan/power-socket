import argparse
from pathlib import Path

from .app import main
from .exporter import (
    ExportError,
    export_from_settings,
    load_export_settings,
    preview_export_redactions,
    preview_selected_export,
)


def cli() -> None:
    parser = argparse.ArgumentParser(prog="power-socket")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("chat", "export"),
        default="chat",
        help="Open the chat UI or create the manually selected dataset archive.",
    )
    args = parser.parse_args()
    if args.command == "chat":
        main()
        return

    root = Path(__file__).resolve().parent.parent
    try:
        settings_path = root / "settings.json"
        if not settings_path.exists():
            print("settings.json is missing; export remains disabled.")
            raise SystemExit(2)
        settings = load_export_settings(settings_path)
        if settings["dataset_export_enabled"] is not True:
            print("Dataset export is DISABLED. Change settings.json explicitly to enable it.")
            raise SystemExit(2)
        selected = settings.get("selected_chats", [])
        folders = settings.get("selected_folders", [])
        print("Selected chats:")
        for name in selected:
            print(f"  - {name}")
        print("Selected folders:")
        for name in folders:
            print(f"  - {name}")
        preview = preview_selected_export(
            root / "data" / "chats", selected, folders
        )
        print("\nExact files that will be included:")
        for name in preview:
            print(f"  - {name}")
        print(f"Total files: {len(preview)}")
        redaction_report = preview_export_redactions(
            root / "data" / "chats", selected, folders, settings["redact_terms"]
        )
        print("\nContent redaction preview:")
        total_redactions = 0
        for item in redaction_report:
            total_redactions += item["redactions"]
            print(f"  - {item['path']}: {item['redactions']} replacements")
        print(f"Total replacements: {total_redactions}")
        print("Automatic patterns: email addresses, phone numbers, IPv4 addresses, common API tokens and bearer tokens.")
        print(f"Custom literal terms configured: {len(settings['redact_terms'])}")
        print("Only exported copies are redacted; original chat files remain unchanged.")
        print("WARNING: redaction is best-effort and cannot guarantee removal of every identity or secret. Review the archive before sharing.")
        answer = input("Type EXPORT to create a local redacted .tar.xz archive (nothing will be uploaded): ")
        if answer != "EXPORT":
            print("Cancelled.")
            return
        archive = export_from_settings(root)
        print(f"Created local archive: {archive}")
    except (ExportError, OSError, ValueError) as exc:
        print(f"Export failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
