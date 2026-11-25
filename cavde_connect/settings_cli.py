"""Interactive terminal menu for dataset-export settings."""

import json
from pathlib import Path
from typing import Callable

from .exporter import ExportError, load_export_settings


def _available_chats(chat_dir: Path) -> list[str]:
    if not chat_dir.exists():
        return []
    return sorted(
        path.relative_to(chat_dir).as_posix()
        for path in chat_dir.rglob("*.jsonl")
        if path.is_file() and not path.is_symlink()
    )


def _available_folders(chat_dir: Path) -> list[str]:
    if not chat_dir.exists():
        return []
    return sorted(
        path.relative_to(chat_dir).as_posix()
        for path in chat_dir.rglob("*")
        if path.is_dir() and not path.is_symlink()
    )


def _parse_numbers(raw: str, maximum: int) -> list[int]:
    numbers = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 1 <= int(part) <= maximum:
            raise ValueError(f"Choose numbers from 1 to {maximum}.")
        number = int(part)
        if number not in numbers:
            numbers.append(number)
    return numbers


def _toggle_paths(
    current: list[str], available: list[str], chosen_numbers: list[int]
) -> list[str]:
    selected = list(current)
    for number in chosen_numbers:
        value = available[number - 1]
        if value in selected:
            selected.remove(value)
        else:
            selected.append(value)
    return sorted(selected)


def _save_settings(path: Path, settings: dict) -> None:
    payload = {
        "dataset_export_enabled": settings["dataset_export_enabled"],
        "selected_chats": settings["selected_chats"],
        "selected_folders": settings["selected_folders"],
        "redact_terms": settings["redact_terms"],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ExportError(f"Cannot save settings: {exc}") from exc


def _choose_paths(
    title: str,
    available: list[str],
    current: list[str],
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> list[str]:
    output_fn(f"\n{title}")
    if not available:
        output_fn("  No matching items found in data/chats.")
        return current
    for index, name in enumerate(available, 1):
        marker = "[x]" if name in current else "[ ]"
        output_fn(f"  {index}. {marker} {name}")
    output_fn("Enter comma-separated numbers to toggle selection, or press Enter to return.")
    raw = input_fn("> ").strip()
    if not raw:
        return current
    try:
        numbers = _parse_numbers(raw, len(available))
    except ValueError as exc:
        output_fn(str(exc))
        return current
    return _toggle_paths(current, available, numbers)


def _edit_redaction_terms(
    settings: dict,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> None:
    while True:
        terms = settings["redact_terms"]
        output_fn("\nCustom redaction terms:")
        if terms:
            for index, term in enumerate(terms, 1):
                output_fn(f"  {index}. {term}")
        else:
            output_fn("  No custom terms configured.")
        output_fn("  [a] Add term  [d] Delete term  [b] Back")
        action = input_fn("> ").strip().lower()
        if action == "b":
            return
        if action == "a":
            term = input_fn("Term to redact (1-200 characters): ").strip()
            if not 0 < len(term) <= 200:
                output_fn("Term must contain 1-200 characters.")
            elif term.casefold() in {item.casefold() for item in terms}:
                output_fn("That term is already configured.")
            elif len(terms) >= 1000:
                output_fn("The maximum is 1000 custom terms.")
            else:
                terms.append(term)
                output_fn("Term added.")
        elif action == "d":
            if not terms:
                output_fn("There are no terms to delete.")
                continue
            raw = input_fn("Term number to delete: ").strip()
            try:
                number = _parse_numbers(raw, len(terms))
                if len(number) != 1:
                    raise ValueError("Enter exactly one term number.")
                removed = terms.pop(number[0] - 1)
                output_fn(f"Removed: {removed}")
            except ValueError as exc:
                output_fn(str(exc))
        else:
            output_fn("Unknown option.")


def run_settings_menu(
    project_root: Path,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Interactively edit and save settings.json."""
    settings_path = project_root / "settings.json"
    chat_dir = project_root / "data" / "chats"
    settings = load_export_settings(settings_path)

    while True:
        output_fn("\n=== Power Socket Settings ===")
        output_fn(
            "Dataset export: "
            + ("ENABLED" if settings["dataset_export_enabled"] else "DISABLED")
        )
        output_fn(f"Selected chats: {len(settings['selected_chats'])}")
        output_fn(f"Selected folders: {len(settings['selected_folders'])}")
        output_fn(f"Custom redaction terms: {len(settings['redact_terms'])}")
        output_fn("  1. Toggle dataset export")
        output_fn("  2. Select chat JSONL files")
        output_fn("  3. Select chat folders")
        output_fn("  4. Manage custom redaction terms")
        output_fn("  5. Save and exit")
        output_fn("  0. Exit without saving")
        action = input_fn("> ").strip()

        if action == "1":
            settings["dataset_export_enabled"] = not settings["dataset_export_enabled"]
        elif action == "2":
            settings["selected_chats"] = _choose_paths(
                "Available chat files",
                _available_chats(chat_dir),
                settings["selected_chats"],
                input_fn,
                output_fn,
            )
        elif action == "3":
            settings["selected_folders"] = _choose_paths(
                "Available chat folders",
                _available_folders(chat_dir),
                settings["selected_folders"],
                input_fn,
                output_fn,
            )
        elif action == "4":
            _edit_redaction_terms(settings, input_fn, output_fn)
        elif action == "5":
            _save_settings(settings_path, settings)
            output_fn(f"Settings saved to {settings_path}")
            return
        elif action == "0":
            output_fn("Changes discarded.")
            return
        else:
            output_fn("Unknown option. Choose 0-5.")
