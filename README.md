# Power Socket

A modular, keyboard-driven terminal client for local and remote AI services.

## Current status

Early development (0.2.0). The project has a Textual interface, profile and JSONL
conversation storage, provider adapters for Ollama and OpenAI-compatible servers,
and an opt-in, manually confirmed dataset export with optional Google Drive upload.

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
Open PowerShell in the Power Socket project directory, then run:
.\.venv\Scripts\python.exe -m power_socket
```

Or double-click `RUN-WINDOWS.bat`.

## Run on Linux and macOS

Make the launcher executable once, then run it:

```bash
chmod +x RUN-LINUXNMACOS.sh
./RUN-LINUXNMACOS.sh
```

The script requires Python 3.10 or newer. On first launch, it creates `.venv`
and installs the dependencies from `requirements.txt`. Later launches reuse that
environment. You can pass CLI commands through the script, for example
`./RUN-LINUXNMACOS.sh settings`.

To create the environment on another Windows machine:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Navigation

Use the **Menu** button to open the main navigation. The Chat section contains
conversation management actions (open, rename, delete, and refresh). Create a
new conversation directly from the main menu. Profile selection, creation,
editing, deletion, and provider configuration are grouped under
**Settings → Profiles**.

The composer is multiline: press **Enter** to send a message and
**Shift+Enter** to insert a new line. The new-conversation dialog has **Back**
and **Continue** actions. Menus use safe internal item IDs and include Back.

### Slash commands

Enter commands directly in the chat composer. They are local UI actions and are
never sent to the AI. Quote names containing spaces.

| Command | Action |
|---|---|
| `/chat new <name>` | Create a conversation |
| `/chat rename <new name>` | Rename the current conversation |
| `/chat rename <old name> <new name>` | Rename another conversation |
| `/chat delete <name>` | Delete a conversation |
| `/chat open <name>` | Open a conversation |
| `/chat refresh` | Refresh the conversation list |
| `/settings profile create <name> <username> <provider> <model> <endpoint> [memory]` | Create a profile; memory defaults to false |
| `/settings profile change` | Select the active profile |
| `/settings profile edit <name> <field> <value>` | Edit username, provider, model, endpoint, or memory |
| `/settings profile delete [name]` | Delete a named profile, or the active one |
| `/settings profile provider current` | Print active provider ID and endpoint |
| `/settings profile provider edit <provider> <endpoint>` | Change active provider ID and endpoint |
| `/model current` | Print the active model |
| `/model change <model name>` | Set the active model |
| `/model edit <temperature> <top_p> <top_k> <context_length> <max_tokens> [thinking]` | Set model parameters; use `none` to leave a numeric value unset |
| `/settings general` | Open general settings |
| `/settings general export` | Open dataset export settings |
| `/settings memory` | Open shared Instructions, Memory, and Skills path settings |
| `/settings export status\|enable\|disable` | Inspect or toggle local dataset export |
| `/settings context show` | Show shared Instructions, Memory, and Skills paths |
| `/settings context set <instructions\|memory\|skills> <path>` | Set a shared resource path (quote paths containing spaces) |
| `/models` | Discover and choose a provider model |
| `/menu` | Open navigation |
| `/status` | Show active profile and conversation |
| `/help` | Show command reference |
| `/quit` | Exit Power Socket |

Example:
`/settings profile create "Coding" "Dev User" ollama qwen3:4b "http://127.0.0.1:11434" false`

For profile editing, valid fields are `username`, `provider`, `model`,
`endpoint`, and `memory`. The memory value must be true or false. The optional thinking value in
`/model edit` must also be true or false. Ollama receives the thinking flag;
OpenAI-compatible adapters currently store it but do not send it.

## Data

- `profiles.jsonl` is the required profile database filename.
- `data/chats/*.jsonl` stores conversations as one input/output pair per line.
- `data/memory/<profile>.md` contains legacy profile-specific memory files.
- `settings.json` controls explicit dataset export and redaction. Google OAuth credentials are stored separately.

Profiles share the chat collection. Only one profile is active at a time.

The shared Instructions / Memory / Skills design and AI-approved Memory editing
are being implemented under `ROADMAP2.md`; the current app still uses the legacy
per-profile memory behavior until that migration is completed. Existing memory
files are preserved during the redesign.

The reserved chat name `profiles` is converted to a short salted-hash name so
it cannot collide with the required `profiles.jsonl` database.

## Providers

- `ollama`: Ollama `/api/chat` endpoint.
- `llamacpp`, `llama.cpp`, `openai_compatible`: OpenAI-compatible
  `/v1/chat/completions` endpoint, suitable for llama.cpp server and compatible APIs.

The OpenAI-compatible adapter reads an optional API key from the
`POWER_SOCKET_API_KEY` environment variable. Do not put API keys in profiles.jsonl.

Third-party Python packages can register adapters through the
`power_socket.providers` entry-point group. The adapter class must inherit
from `Provider` and implement `generate(model, messages, endpoint)`; optional
model discovery can be implemented with `list_models(endpoint)`. The adapter
may bridge to a native library, a local process, or a network service, so no
universal transport is forced. See `adapters/README.md` for the entry-point
declaration format.

## Dataset export and Google Drive upload

Export is disabled by default in `settings.json`:

```json
{
  "dataset_export_enabled": false,
  "selected_chats": [],
  "selected_folders": [],
  "redact_terms": []
}
```

Configure dataset export interactively with:

```powershell
.\.venv\Scripts\python.exe -m power_socket settings
```

The settings menu lets you enable or disable export, select individual JSONL
chats or folders, and manage custom redaction terms. Folder selections include
their nested `.jsonl` chat files. You can still edit `settings.json` manually if
preferred. Every folder component and filename in the archive is anonymized.
Then run:

```powershell
.\.venv\Scripts\python.exe -m power_socket export
```

The program previews the exact selected files and estimates content
redactions before requiring the exact confirmation `EXPORT`. It creates a local
`.tar.xz` archive in `exports/`. Nothing is transmitted by the normal export
command.

### Google Drive OAuth setup (developer configuration)

Power Socket uses Google's **installed desktop app OAuth flow** and the
limited `drive.file` scope. Each user signs in with their own Google account;
the uploaded archive is created in that user's Drive. The app does not use a
shared upload token or the developer's Drive.

For local development:

1. In Google Cloud Console, create/select a project and enable the **Google Drive API**.
2. Configure the OAuth consent screen and add your Google account as a test user while the app is in Testing.
3. Create an OAuth client ID with application type **Desktop app**.
4. Download its JSON and place it at the project root as `client_secret.json`.
   This filename is ignored by Git. Alternatively set
   `POWER_SOCKET_GOOGLE_OAUTH_CLIENT_FILE` to its path.
5. Install dependencies with `python -m pip install -r requirements.txt`.

The OAuth client configuration is app-wide developer configuration, not a
per-user API key. Do not commit the downloaded JSON to the repository. Before
distributing Power Socket publicly, configure the OAuth consent screen for the
intended audience and complete Google's verification requirements if required.
While the consent screen is in Testing, only listed test users can authorize it.

To create the archive and then explicitly upload it:

```powershell
.\.venv\Scripts\python.exe -m power_socket export --upload
```

Power Socket first asks for `EXPORT` to create the local archive, then separately
asks for `UPLOAD`. It opens the user's browser for Google sign-in the first time;
subsequent uploads reuse the local refresh token and refresh access automatically.
The token is stored under the user's OS application-data directory, outside the
project and Git repository. The upload uses the Drive API's resumable upload
mechanism and creates one archive file in the signed-in user's Drive.

To revoke the app's access, remove Power Socket from the connected apps in the
Google Account security settings. Deleting the local token file also signs the
local installation out, but does not revoke Google's grant by itself.

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
Exports are limited to 100 files and 50 MiB of source/redacted data.

**Important:** automatic redaction is best-effort, not a guarantee. It cannot
reliably recognize every person's name, school, location, or secret. Review the
redaction preview and inspect the resulting archive before sharing it.

## Resource policy

The app does not launch local model servers, download models, benchmark hardware,
or scan disks. Network calls happen only when the user sends a message through a
configured provider or explicitly confirms a Google Drive upload. Dataset export
and upload are manually initiated and size-limited.
