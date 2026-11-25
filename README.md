# Power Socket

A modular, keyboard-driven terminal client for local and remote AI services.

## Current status

Early development (0.2.0). The project has a Textual interface, profile and JSONL
conversation storage, provider adapters for Ollama and OpenAI-compatible servers,
and a local-only, manually confirmed dataset export command.

## Requirements

- Python 3.10 or newer is declared by the package; currently verified runtimes are Python 3.12, 3.13, and 3.14 on Windows.
- Debian 13 (Python 3.13.5) has also passed the full test suite under WSL.
- A terminal that supports Textual.
- A provider service such as Ollama or a compatible llama.cpp server for live chat.

macOS-specific editor launching is covered by a mocked platform test, but no
macOS machine is currently available for an end-to-end verification. A GitHub
Actions matrix is configured for Windows, Ubuntu, and macOS with Python 3.12-3.14;
the macOS runner has not executed yet.

No C/C++ or Rust compiler is required for the current Python application.

## Run on Windows

```powershell
cd D:\cavde.connect
.\.venv\Scripts\python.exe -m cavde_connect
```

Or double-click `RUN-WINDOWS.bat`.

To create the environment on another Windows machine:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+N | New chat |
| Ctrl+M | Rename active chat |
| Ctrl+D | Delete active chat (confirmation required) |
| Ctrl+Shift+P | Create profile |
| Ctrl+Shift+X | Delete active profile (confirmation required; memory file is retained) |
| Ctrl+E | Edit active profile |
| Ctrl+Shift+M | Open active profile memory in the system editor |
| Ctrl+L | Load available models from the active provider |
| Ctrl+P | Focus profile list |
| Ctrl+R | Refresh chat list |
| Ctrl+Q | Quit |

Use arrow keys and Enter to select profiles and chats.

## Data

- `profiles.jsonl` is the required profile database filename.
- `data/chats/*.jsonl` stores conversations as one input/output pair per line.
- `data/memory/<profile>.md` stores profile-specific memory.
- `settings.json` controls explicit dataset export.

Profiles share the chat collection. Only one profile is active at a time.
Memory is kept separate by profile. Memory files are read-only context for the
assistant; Power Socket does not silently write chat content into them.

The reserved chat name `profiles` is converted to a short salted-hash name so
it cannot collide with the required `profiles.jsonl` database.

## Providers

- `ollama`: Ollama `/api/chat` endpoint.
- `llamacpp`, `llama.cpp`, `openai_compatible`: OpenAI-compatible
  `/v1/chat/completions` endpoint, suitable for llama.cpp server and compatible APIs.

The OpenAI-compatible adapter reads an optional API key from the
`POWER_SOCKET_API_KEY` environment variable. The legacy `CAVDE_CONNECT_API_KEY` name remains supported. Do not put API keys in profiles.jsonl.

Third-party Python packages can register adapters through the
`cavde_connect.providers` entry-point group. The adapter class must inherit
from `Provider` and implement `generate(model, messages, endpoint)`; optional
model discovery can be implemented with `list_models(endpoint)`. The adapter
may bridge to a native library, a local process, or a network service, so no
universal transport is forced. See `adapters/README.md` for the entry-point
declaration format.

## Dataset export and privacy

Export is disabled by default in `settings.json`:

```json
{
  "dataset_export_enabled": false,
  "selected_chats": [],
  "selected_folders": [],
  "redact_terms": []
}
```

To prepare an export, manually set `dataset_export_enabled` to `true` and list
the exact chat names in `selected_chats` and/or relative folder names in
`selected_folders`. Folder selections include their nested `.jsonl` chat files.
Every folder component and filename in the archive is anonymized. Then run:

```powershell
.\.venv\Scripts\python.exe -m cavde_connect export
```

The program previews the exact selected files and estimates content
redactions before requiring the exact confirmation `EXPORT`. It creates a local
`.tar.xz` archive in `exports/`; it never uploads or sends anything. Archive
entry names are twelve-character salted-hash fragments derived using fresh
random UUIDs, with collisions checked within each archive. Tar ownership,
permissions, and timestamps are normalized.

Exported JSONL copies automatically redact common email addresses, phone
numbers, IPv4 addresses, common API-token formats, and Bearer tokens. Add
project-specific names, usernames, school names, or other literal terms to
`redact_terms` in `settings.json`:

```json
{
  "dataset_export_enabled": false,
  "selected_chats": [],
  "selected_folders": [],
  "redact_terms": ["Your name", "Private project name"]
}
```

Custom terms are matched case-insensitively as literal substrings and
replaced with `[REDACTED:custom]`; choose distinctive terms to avoid
over-redacting. Redaction only affects the exported copy; original chats remain
unchanged. Malformed JSONL is rejected and partial archives are removed.
Exports are limited to 100 files and 50 MiB.

**Important:** automatic redaction is best-effort, not a guarantee. It cannot
reliably recognize every person's name, school, location, or secret. Review the
redaction preview and inspect the resulting archive before sharing it.

## Resource policy

The app does not launch local model servers, download models, benchmark hardware,
or scan disks. Network calls happen only when the user sends a message through a
configured provider. Export is manually initiated and size-limited.
