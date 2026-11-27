import json
import tempfile
import unittest
from pathlib import Path

from power_socket.settings_cli import run_settings_menu


class SettingsCliTests(unittest.TestCase):
    def test_menu_selects_chat_folder_and_redaction_term(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "data" / "chats"
            nested = chats / "collection"
            nested.mkdir(parents=True)
            (chats / "first.jsonl").write_text(
                '{"input":"hello","output":"hi"}\n', encoding="utf-8"
            )
            (nested / "second.jsonl").write_text(
                '{"input":"hello","output":"hi"}\n', encoding="utf-8"
            )
            (root / "settings.json").write_text(
                json.dumps({
                    "dataset_export_enabled": False,
                    "selected_chats": [],
                    "selected_folders": [],
                    "redact_terms": [],
                }),
                encoding="utf-8",
            )
            answers = iter(["1", "2", "2", "3", "1", "4", "a", "Private Name", "b", "5"])
            output = []
            run_settings_menu(root, lambda _prompt: next(answers), output.append)

            settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
            self.assertTrue(settings["dataset_export_enabled"])
            self.assertEqual(settings["selected_chats"], ["first.jsonl"])
            self.assertEqual(settings["selected_folders"], ["collection"])
            self.assertEqual(settings["redact_terms"], ["Private Name"])
            self.assertTrue(any("Settings saved" in line for line in output))

    def test_exit_without_saving_preserves_original_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.mkdir(exist_ok=True)
            original = {
                "dataset_export_enabled": False,
                "selected_chats": [],
                "selected_folders": [],
                "redact_terms": [],
            }
            (root / "settings.json").write_text(json.dumps(original), encoding="utf-8")
            answers = iter(["1", "0"])
            run_settings_menu(root, lambda _prompt: next(answers), lambda _line: None)
            actual = json.loads((root / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(actual, original)


if __name__ == "__main__":
    unittest.main()
