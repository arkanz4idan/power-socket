"""Google Drive upload using per-user OAuth (installed desktop application)."""

import json
import os
from pathlib import Path


CHUNK_SIZE = 4 * 1024 * 1024
DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive.file"]


class DriveUploadError(Exception):
    """Raised when Google Drive authentication or upload fails."""


def default_client_secrets_path() -> Path:
    configured = os.environ.get("POWER_SOCKET_GOOGLE_OAUTH_CLIENT_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parent.parent / "client_secret.json"


def default_token_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "PowerSocket" / "google-drive-token.json"


def _validate_client_file(path: Path) -> None:
    if not path.is_file():
        raise DriveUploadError(
            "Google OAuth client file is missing. Place your Desktop-app OAuth "
            "client JSON at client_secret.json, or set "
            "POWER_SOCKET_GOOGLE_OAUTH_CLIENT_FILE."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DriveUploadError(f"Cannot read Google OAuth client file: {exc}") from exc
    installed = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(installed, dict) or not installed.get("client_id") or not installed.get("client_secret"):
        raise DriveUploadError(
            "OAuth client JSON must be a Google Cloud Desktop app (installed) client."
        )


def _load_credentials(client_file: Path, token_file: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise DriveUploadError(
            "Google Drive support is not installed. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    credentials = None
    if token_file.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(token_file), DRIVE_SCOPE
            )
        except (OSError, ValueError, json.JSONDecodeError):
            credentials = None

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file),
            DRIVE_SCOPE,
            autogenerate_code_verifier=True,
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            authorization_prompt_message=(
                "Open this URL in your browser to connect Google Drive: {url}"
            ),
            success_message=(
                "Google Drive connected. You can close this browser tab."
            ),
            access_type="offline",
            prompt="consent",
        )

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    if os.name != "nt":
        try:
            token_file.chmod(0o600)
        except OSError:
            pass
    return credentials


def upload_archive_to_drive(
    archive: Path,
    client_secrets_file: Path | None = None,
    token_file: Path | None = None,
) -> dict:
    """Authenticate the current user and upload one archive to their Drive."""
    archive = Path(archive)
    if not archive.is_file():
        raise DriveUploadError("Archive does not exist.")
    if archive.stat().st_size <= 0:
        raise DriveUploadError("Archive is empty.")

    client_file = Path(client_secrets_file or default_client_secrets_path())
    saved_token = Path(token_file or default_token_path())
    _validate_client_file(client_file)
    credentials = _load_credentials(client_file, saved_token)

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise DriveUploadError(
            "Google Drive support is not installed. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    try:
        service = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        media = MediaFileUpload(
            str(archive),
            mimetype="application/x-xz",
            resumable=True,
            chunksize=CHUNK_SIZE,
        )
        request = service.files().create(
            body={"name": archive.name},
            media_body=media,
            fields="id,name,mimeType,size,webViewLink,createdTime",
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status is not None:
                print(f"Uploading to your Google Drive: {int(status.progress() * 100)}%")

        return response
    except Exception as exc:
        raise DriveUploadError(f"Google Drive upload failed: {exc}") from exc
