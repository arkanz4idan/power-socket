import hashlib
import json
import re
import secrets
from pathlib import Path
from typing import Iterator

from .models import Profile


class StorageError(Exception):
    """Raised when persisted user data is invalid or cannot be accessed."""


def _read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise StorageError(f"{path.name}:{line_number}: invalid JSON: {exc}") from exc
                if not isinstance(value, dict):
                    raise StorageError(f"{path.name}:{line_number}: each JSONL line must be an object")
                yield value
    except OSError as exc:
        raise StorageError(f"Cannot read {path}: {exc}") from exc


def load_profiles(path: Path) -> list[Profile]:
    profiles: list[Profile] = []
    seen: set[str] = set()
    for item in _read_jsonl(path):
        required = ("Profilename", "Username", "provider", "currentmodel", "memory")
        if any(key not in item for key in required):
            raise StorageError(f"Profile entry is missing one of: {', '.join(required)}")
        memory = item["memory"]
        if not isinstance(memory, list) or len(memory) != 2 or not isinstance(memory[0], bool):
            raise StorageError("Profile 'memory' must be [enabled: bool, path: str]")
        name = str(item["Profilename"]).strip()
        key = name.casefold()
        if not name or key in seen:
            raise StorageError(f"Empty or duplicate profile name: {name!r}")
        seen.add(key)
        profiles.append(Profile(
            profilename=name,
            username=str(item["Username"]),
            provider=str(item["provider"]).lower(),
            currentmodel=str(item["currentmodel"]),
            memory_enabled=memory[0],
            memory_path=str(memory[1]),
            endpoint=str(item.get("endpoint", "http://127.0.0.1:11434")),
        ))
    return profiles


def save_profiles(path: Path, profiles: list[Profile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            for profile in profiles:
                item = {
                    "Profilename": profile.profilename,
                    "Username": profile.username,
                    "provider": profile.provider,
                    "currentmodel": profile.currentmodel,
                    "memory": [profile.memory_enabled, profile.memory_path],
                    "endpoint": profile.endpoint,
                }
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        temp.replace(path)
    except OSError as exc:
        raise StorageError(f"Cannot save profiles: {exc}") from exc


def validate_chat_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Chat name cannot be empty")
    windows_reserved = {"CON", "PRN", "AUX", "NUL"}
    windows_reserved.update(f"COM{number}" for number in range(1, 10))
    windows_reserved.update(f"LPT{number}" for number in range(1, 10))
    if cleaned.casefold() == "profiles" or cleaned.upper() in windows_reserved:
        salt = secrets.token_bytes(16)
        digest = hashlib.sha256(salt + cleaned.encode("utf-8")).hexdigest()
        cleaned = "blocked-" + digest[:10]
    if not re.fullmatch(r"[\w .()-]{1,64}", cleaned, flags=re.UNICODE):
        raise ValueError("Use 1-64 letters, numbers, spaces, dots, parentheses, _ or -")
    return cleaned


def chat_path(chat_dir: Path, name: str) -> Path:
    safe_name = validate_chat_name(name)
    return chat_dir / f"{safe_name}.jsonl"


def list_chats(chat_dir: Path) -> list[str]:
    chat_dir.mkdir(parents=True, exist_ok=True)
    return sorted(path.stem for path in chat_dir.glob("*.jsonl") if path.is_file())


def load_chat(path: Path) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in _read_jsonl(path):
        if "input" not in item or "output" not in item:
            raise StorageError(f"{path.name}: each chat row needs 'input' and 'output'")
        messages.append({"input": str(item["input"]), "output": str(item["output"])})
    return messages


def append_chat_turn(path: Path, user_input: str, ai_output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"input": user_input, "output": ai_output}, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise StorageError(f"Cannot append conversation: {exc}") from exc


def rename_chat(chat_dir: Path, old_name: str, new_name: str) -> str:
    source = chat_path(chat_dir, old_name)
    destination = chat_path(chat_dir, new_name)
    if not source.is_file():
        raise FileNotFoundError(f"Chat not found: {old_name}")
    if destination.exists() and destination != source:
        raise FileExistsError(f"Chat already exists: {destination.stem}")
    source.rename(destination)
    return destination.stem


def delete_chat(chat_dir: Path, name: str) -> None:
    target = chat_path(chat_dir, name)
    if not target.is_file():
        raise FileNotFoundError(f"Chat not found: {name}")
    target.unlink()
