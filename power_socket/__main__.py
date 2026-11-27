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
from .google_drive import DriveUploadError, upload_archive_to_drive
from .settings_cli import run_settings_menu


def cli() -> None:
    parser = argparse.ArgumentParser(prog="power-socket")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("chat", "export", "settings"),
        default="chat",
        help="Open chat, configure settings, or create a dataset archive.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="After creating the archive, explicitly offer upload to Google Drive.",
    )
    args = parser.parse_args()
    if args.command == "chat":
        if args.upload:
            parser.error("--upload can only be used with the export command.")
        main()
        return

    root = Path(__file__).resolve().parent.parent
    if args.command == "settings":
        if args.upload:
            parser.error("--upload can only be used with the export command.")
        try:
            run_settings_menu(root)
        except (ExportError, OSError, ValueError) as exc:
            print(f"Settings error: {exc}")
            raise SystemExit(1) from exc
        return

    try:
        settings_path = root / "settings.json"
        if not settings_path.exists():
            print("settings.json is missing; export remains disabled.")
            raise SystemExit(2)
        settings = load_export_settings(settings_path)
        if settings["dataset_export_enabled"] is not True:
            print("Dataset export is DISABLED. Run 'python -m power_socket settings' to enable it.")
            raise SystemExit(2)

        selected = settings.get("selected_chats", [])
        folders = settings.get("selected_folders", [])
        if not selected and not folders:
            print("No chats or folders selected.")
            print("Run 'python -m power_socket settings' to choose JSONL files or folders.")
            raise SystemExit(2)

        print("Selected chats:")
        for name in selected:
            print(f"  - {name}")
        print("Selected folders:")
        for name in folders:
            print(f"  - {name}")
        preview = preview_selected_export(root / "data" / "chats", selected, folders)
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
        answer = input("Type EXPORT to create the local redacted .tar.xz archive: ")
        if answer != "EXPORT":
            print("Cancelled.")
            return

        archive = export_from_settings(root)
        print(f"Created local archive: {archive}")

        if args.upload:
            print("\nPower Socket will open Google sign-in and upload this archive to your own Drive.")
            answer = input("Type UPLOAD to connect Google Drive and transmit this archive: ")
            if answer != "UPLOAD":
                print("Upload cancelled. The local archive was kept.")
                return
            result = upload_archive_to_drive(archive)
            print(f"Uploaded to your Google Drive: {result.get('name', archive.name)}")
            if result.get("webViewLink"):
                print(f"Open in Drive: {result['webViewLink']}")
            elif result.get("id"):
                print(f"Drive file ID: {result['id']}")
    except (ExportError, DriveUploadError, OSError, ValueError) as exc:
        print(f"Export failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
