import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cavde_connect.google_drive import (
    DriveUploadError,
    _validate_client_file,
    default_token_path,
)


class GoogleDriveConfigTests(unittest.TestCase):
    def test_requires_desktop_app_oauth_client_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "client_secret.json"
            path.write_text(json.dumps({"web": {"client_id": "id"}}), encoding="utf-8")
            with self.assertRaises(DriveUploadError):
                _validate_client_file(path)

    def test_accepts_installed_desktop_app_oauth_client_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "client_secret.json"
            path.write_text(json.dumps({
                "installed": {
                    "client_id": "example.apps.googleusercontent.com",
                    "client_secret": "not-a-real-secret",
                }
            }), encoding="utf-8")
            _validate_client_file(path)

    def test_rejects_missing_client_file(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(DriveUploadError):
                _validate_client_file(Path(temp) / "missing.json")

    def test_windows_token_path_is_outside_project(self):
        with patch("cavde_connect.google_drive.os.name", "nt"), patch.dict(
            os.environ, {"APPDATA": "C:/Users/test/AppData/Roaming"}
        ):
            path = default_token_path()
        self.assertEqual(
            path,
            Path("C:/Users/test/AppData/Roaming/PowerSocket/google-drive-token.json"),
        )


if __name__ == "__main__":
    unittest.main()
