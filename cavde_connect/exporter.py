"""Explicit, local-only JSONL dataset export."""

import hashlib
import json
import os
import re
import secrets
import tarfile
import tempfile
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath

class ExportError(Exception):
    """Raised when a selected dataset cannot be exported safely."""


MAX_EXPORT_FILES = 100
MAX_EXPORT_BYTES = 50 * 1024 * 1024
REDACTION_PATTERNS = (
    ("email", re.compile(
        r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    )),
    ("phone", re.compile(
        r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:0?8\d{1,3}|0[2-9]\d{1,2})[ .-]?\d{3,4}[ .-]?\d{3,5}(?!\w)"
    )),
    ("ip", re.compile(
        r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"
    )),
    ("secret", re.compile(
        r"(?i)\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16})\b"
    )),
    ("bearer", re.compile(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}"
    )),
)


def load_export_settings(path: Path) -> dict:
    if not path.exists():
        return {
            "dataset_export_enabled": False,
            "selected_chats": [],
            "selected_folders": [],
            "redact_terms": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"Cannot read export settings: {exc}") from exc
    if not isinstance(data, dict):
        raise ExportError("settings.json must contain a JSON object")
    enabled = data.get("dataset_export_enabled", False)
    chats = data.get("selected_chats", [])
    folders = data.get("selected_folders", [])
    redact_terms = data.get("redact_terms", [])
    if (
        not isinstance(enabled, bool)
        or not isinstance(chats, list)
        or not all(isinstance(name, str) for name in chats)
        or not isinstance(folders, list)
        or not all(isinstance(name, str) for name in folders)
        or not isinstance(redact_terms, list)
        or len(redact_terms) > 1000
        or not all(isinstance(term, str) and 0 < len(term) <= 200 for term in redact_terms)
    ):
        raise ExportError("Invalid export settings types or redaction terms")
    return {
        "dataset_export_enabled": enabled,
        "selected_chats": chats,
        "selected_folders": folders,
        "redact_terms": redact_terms,
    }


def _relative_parts(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    raw_parts = normalized.split("/")
    if (
        not normalized
        or path.is_absolute()
        or ":" in normalized
        or not path.parts
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise ExportError(f"Unsafe relative selection: {value!r}")
    return tuple(raw_parts)


def _resolve_inside(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ExportError(f"Symbolic links are not allowed in exports: {current.name}")
    try:
        resolved = current.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ExportError(f"Selected path does not exist: {'/'.join(parts)}") from exc
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ExportError("Selected path escapes the chat directory") from exc
    return resolved


def _collect_selected_files(
    chat_dir: Path,
    selected_chats: list[str],
    selected_folders: list[str],
) -> list[tuple[Path, tuple[str, ...]]]:
    root = chat_dir.resolve(strict=True)
    selected: dict[str, tuple[Path, tuple[str, ...]]] = {}

    for name in selected_chats:
        raw_parts = _relative_parts(name)
        filename = raw_parts[-1]
        if filename.casefold().endswith(".jsonl"):
            parts = raw_parts
        else:
            parts = (*raw_parts[:-1], filename + ".jsonl")
        source = _resolve_inside(root, parts)
        if not source.is_file():
            raise ExportError(f"Selected chat is not a file: {name}")
        relative = source.relative_to(root).parts
        selected[source.as_posix()] = (source, relative)

    for folder_name in selected_folders:
        parts = _relative_parts(folder_name)
        folder = _resolve_inside(root, parts)
        if not folder.is_dir():
            raise ExportError(f"Selected folder does not exist: {folder_name}")
        for current_root, dir_names, file_names in os.walk(folder, followlinks=False):
            current = Path(current_root)
            for directory in list(dir_names):
                candidate = current / directory
                if candidate.is_symlink():
                    raise ExportError(f"Symbolic links are not allowed in exports: {candidate.name}")
            for filename in file_names:
                source = current / filename
                if source.is_symlink():
                    raise ExportError(f"Symbolic links are not allowed in exports: {source.name}")
                if source.suffix.lower() != ".jsonl":
                    continue
                resolved = source.resolve(strict=True)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ExportError("A folder entry escapes the chat directory") from exc
                relative = resolved.relative_to(root).parts
                selected[resolved.as_posix()] = (resolved, relative)

    if not selected:
        raise ExportError("No JSONL chat files found in the selected chats or folders")
    return sorted(selected.values(), key=lambda item: item[1])


def _validate_export_entries(entries: list[tuple[Path, tuple[str, ...]]]) -> None:
    if len(entries) > MAX_EXPORT_FILES:
        raise ExportError(f"Select no more than {MAX_EXPORT_FILES} chat files per archive")
    total_bytes = sum(source.stat().st_size for source, _ in entries)
    if total_bytes > MAX_EXPORT_BYTES:
        raise ExportError("Selected chats exceed the 50 MiB export safety limit")


def _validate_redact_terms(redact_terms: list[str] | None) -> list[str]:
    terms = redact_terms or []
    if (
        not isinstance(terms, list)
        or len(terms) > 1000
        or not all(isinstance(term, str) and 0 < len(term) <= 200 for term in terms)
    ):
        raise ExportError("Redaction terms must be 1-200 characters each (maximum 1000 terms)")
    return terms


def preview_selected_export(
    chat_dir: Path,
    selected_chats: list[str],
    selected_folders: list[str] | None = None,
) -> list[str]:
    """Return the exact relative chat paths that an export would include."""
    entries = _collect_selected_files(chat_dir, selected_chats, selected_folders or [])
    _validate_export_entries(entries)
    return [PurePosixPath(*relative).as_posix() for _, relative in entries]


def _redact_text(text: str, redact_terms: list[str]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    result = text
    for label, pattern in REDACTION_PATTERNS:
        result, count = pattern.subn(f"[REDACTED:{label}]", result)
        if count:
            counts[label] = counts.get(label, 0) + count
    for term in sorted(set(redact_terms), key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result, count = pattern.subn("[REDACTED:custom]", result)
        if count:
            counts["custom"] = counts.get("custom", 0) + count
    return result, counts


def _redact_value(value, redact_terms: list[str], counts: dict[str, int]):
    if isinstance(value, str):
        redacted, found = _redact_text(value, redact_terms)
        for label, count in found.items():
            counts[label] = counts.get(label, 0) + count
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, redact_terms, counts) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_value(item, redact_terms, counts)
            for key, item in value.items()
        }
    return value


def _redacted_jsonl(source: Path, redact_terms: list[str]):
    """Create a spooled, redacted JSONL copy without modifying the source."""
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    counts: dict[str, int] = {}
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ExportError(
                        f"{source.name}:{line_number}: invalid JSONL; export cancelled"
                    ) from exc
                if not isinstance(row, dict) or "input" not in row or "output" not in row:
                    raise ExportError(
                        f"{source.name}:{line_number}: expected input/output object; export cancelled"
                    )
                row["input"] = str(row["input"])
                row["output"] = str(row["output"])
                safe_row = _redact_value(row, redact_terms, counts)
                spool.write(
                    (json.dumps(safe_row, ensure_ascii=False) + "\n").encode("utf-8")
                )
        spool.seek(0)
        return spool, counts
    except (OSError, UnicodeDecodeError) as exc:
        spool.close()
        raise ExportError(f"Cannot safely read {source.name}: {exc}") from exc
    except Exception:
        spool.close()
        raise


def preview_export_redactions(
    chat_dir: Path,
    selected_chats: list[str],
    selected_folders: list[str] | None = None,
    redact_terms: list[str] | None = None,
) -> list[dict]:
    """Count redactions per selected file without writing or changing source data."""
    terms = _validate_redact_terms(redact_terms)
    entries = _collect_selected_files(chat_dir, selected_chats, selected_folders or [])
    _validate_export_entries(entries)
    report = []
    for source, relative in entries:
        spool, counts = _redacted_jsonl(source, terms)
        spool.close()
        report.append({
            "path": PurePosixPath(*relative).as_posix(),
            "redactions": sum(counts.values()),
            "categories": counts,
        })
    return report


def _hash_fragment(salt: bytes, identity: str, used: set[str]) -> str:
    while True:
        random_id = uuid.uuid4().bytes
        digest = hashlib.sha256(salt + random_id + identity.encode("utf-8")).hexdigest()
        candidate = digest[:12]
        if candidate not in used:
            used.add(candidate)
            return candidate


def create_selected_export(
    chat_dir: Path,
    output_dir: Path,
    selected_names: list[str],
    selected_folders: list[str] | None = None,
    redact_terms: list[str] | None = None,
) -> Path:
    """Create a local archive with anonymized paths and redacted JSONL content."""
    selected_folders = selected_folders or []
    redact_terms = _validate_redact_terms(redact_terms)
    if not selected_names and not selected_folders:
        raise ExportError("No chats or folders selected in settings.json")

    entries = _collect_selected_files(chat_dir, selected_names, selected_folders)
    _validate_export_entries(entries)

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = output_dir / f"cavde-dataset-{stamp}.tar.xz"
    salt = secrets.token_bytes(32)
    folder_map: dict[str, str] = {}
    used_folder_names: dict[str, set[str]] = {}
    used_file_names: dict[str, set[str]] = {}

    try:
        exported_bytes = 0
        with tarfile.open(archive, mode="w:xz", preset=1) as bundle:
            for source, relative_parts in entries:
                anonymous_parts: list[str] = []
                original_parent: list[str] = []
                anonymous_parent: list[str] = []
                for part in relative_parts[:-1]:
                    original_parent.append(part)
                    key = "/".join(original_parent)
                    if key not in folder_map:
                        parent_key = "/".join(original_parent[:-1])
                        used = used_folder_names.setdefault(parent_key, set())
                        folder_map[key] = _hash_fragment(salt, key, used)
                    anonymous = folder_map[key]
                    anonymous_parts.append(anonymous)
                    anonymous_parent.append(anonymous)

                parent_key = "/".join(anonymous_parent)
                used_files = used_file_names.setdefault(parent_key, set())
                original_file = "/".join(relative_parts)
                anonymous_file = _hash_fragment(salt, original_file, used_files) + ".jsonl"
                arcname = PurePosixPath(*anonymous_parts, anonymous_file).as_posix()
                redacted_file, _ = _redacted_jsonl(source, redact_terms or [])
                try:
                    info = tarfile.TarInfo(name=arcname)
                    info.size = redacted_file.seek(0, os.SEEK_END)
                    exported_bytes += info.size
                    if exported_bytes > MAX_EXPORT_BYTES:
                        raise ExportError("Redacted archive exceeds the 50 MiB export safety limit")
                    redacted_file.seek(0)
                    info.mode = 0o600
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    bundle.addfile(info, redacted_file)
                finally:
                    redacted_file.close()
    except ExportError:
        try:
            archive.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except (OSError, tarfile.TarError) as exc:
        try:
            archive.unlink(missing_ok=True)
        except OSError:
            pass
        raise ExportError(f"Could not create archive: {exc}") from exc
    return archive


def export_from_settings(project_root: Path) -> Path:
    settings = load_export_settings(project_root / "settings.json")
    if not settings["dataset_export_enabled"]:
        raise ExportError(
            "Dataset export is disabled. Set dataset_export_enabled to true in settings.json first."
        )
    return create_selected_export(
        project_root / "data" / "chats",
        project_root / "exports",
        settings["selected_chats"],
        settings["selected_folders"],
        settings["redact_terms"],
    )
