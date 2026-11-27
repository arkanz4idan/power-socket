import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from power_socket.exporter import (
    ExportError, create_selected_export, load_export_settings,
    preview_export_redactions, preview_selected_export,
)


class ExportTests(unittest.TestCase):
    def test_export_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = load_export_settings(Path(temp) / "missing.json")
            self.assertFalse(settings["dataset_export_enabled"])
            self.assertEqual(settings["selected_chats"], [])
            self.assertEqual(settings["selected_folders"], [])
            self.assertEqual(settings["redact_terms"], [])

    def test_load_export_settings_validates_custom_redaction_terms(self):
        with tempfile.TemporaryDirectory() as temp:
            settings_path = Path(temp) / "settings.json"
            settings_path.write_text(json.dumps({
                "dataset_export_enabled": False,
                "selected_chats": [],
                "selected_folders": [],
                "redact_terms": ["Private Name", "School"],
            }), encoding="utf-8")
            settings = load_export_settings(settings_path)
            self.assertEqual(settings["redact_terms"], ["Private Name", "School"])
            settings_path.write_text(json.dumps({
                "dataset_export_enabled": False,
                "redact_terms": [""],
            }), encoding="utf-8")
            with self.assertRaises(ExportError):
                load_export_settings(settings_path)

    def test_export_only_selected_chat_and_anonymizes_archive_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            chats.mkdir()
            (chats / "chosen.jsonl").write_text(
                json.dumps({"input": "hello", "output": "hi"}) + "\n", encoding="utf-8"
            )
            (chats / "not-selected.jsonl").write_text(
                json.dumps({"input": "private", "output": "data"}) + "\n", encoding="utf-8"
            )
            archive = create_selected_export(chats, root / "exports", ["chosen"])
            with tarfile.open(archive, "r:xz") as bundle:
                members = bundle.getnames()
            self.assertEqual(len(members), 1)
            self.assertTrue(members[0].endswith(".jsonl"))
            self.assertNotIn("chosen", members[0])
            self.assertNotIn("not-selected", members[0])

    def test_folder_export_anonymizes_folder_and_each_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            nested = chats / "private-collection" / "inner-folder"
            nested.mkdir(parents=True)
            (nested / "first-chat.jsonl").write_text('{"input":"a","output":"b"}\n', encoding="utf-8")
            (nested / "second-chat.jsonl").write_text('{"input":"c","output":"d"}\n', encoding="utf-8")
            archive = create_selected_export(chats, root / "exports", [], ["private-collection"])
            with tarfile.open(archive, "r:xz") as bundle:
                members = bundle.getnames()
            self.assertEqual(len(members), 2)
            self.assertTrue(all("private-collection" not in item for item in members))
            self.assertTrue(all("inner-folder" not in item for item in members))
            self.assertEqual({item.split("/")[0] for item in members}.__len__(), 1)
            self.assertTrue(all(len(Path(item).stem) == 12 for item in members))

    def test_export_redacts_common_sensitive_values_and_custom_terms(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            chats.mkdir()
            source = chats / "private.jsonl"
            original = {
                "input": "Contact me at person@example.com or 081234567890",
                "output": "Token sk-12345678901234567890 from Arkan at 192.168.1.10",
                "metadata": {"note": "Arkan"},
            }
            source.write_text(json.dumps(original) + "\n", encoding="utf-8")
            report = preview_export_redactions(chats, ["private"], redact_terms=["Arkan"])
            self.assertEqual(report[0]["redactions"], 6)
            archive = create_selected_export(
                chats, root / "exports", ["private"], redact_terms=["Arkan"]
            )
            with tarfile.open(archive, "r:xz") as bundle:
                member = bundle.getmembers()[0]
                exported = json.loads(bundle.extractfile(member).read().decode("utf-8"))
            self.assertIn("[REDACTED:email]", exported["input"])
            self.assertIn("[REDACTED:phone]", exported["input"])
            self.assertIn("[REDACTED:secret]", exported["output"])
            self.assertIn("[REDACTED:ip]", exported["output"])
            self.assertEqual(exported["metadata"]["note"], "[REDACTED:custom]")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), original)
            self.assertEqual((member.uid, member.gid, member.uname, member.gname, member.mtime),
                             (0, 0, "", "", 0))
            self.assertEqual(member.mode, 0o600)

    def test_export_rejects_malformed_jsonl_without_leaking_partial_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            chats.mkdir()
            (chats / "broken.jsonl").write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaises(ExportError):
                create_selected_export(chats, root / "exports", ["broken"])
            self.assertEqual(list((root / "exports").glob("*.tar.xz")), [])

    def test_export_preview_lists_exact_selected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            nested = chats / "folder"
            nested.mkdir(parents=True)
            (chats / "chosen.jsonl").write_text("", encoding="utf-8")
            (nested / "nested.jsonl").write_text("", encoding="utf-8")
            (chats / "not-selected.jsonl").write_text("", encoding="utf-8")
            preview = preview_selected_export(chats, ["chosen"], ["folder"])
            self.assertEqual(preview, ["chosen.jsonl", "folder/nested.jsonl"])
            self.assertNotIn("not-selected.jsonl", preview)

    def test_export_rejects_missing_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "chats").mkdir()
            with self.assertRaises(ExportError):
                create_selected_export(root / "chats", root / "exports", ["missing"])

    def test_export_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chats = root / "chats"
            chats.mkdir()
            with self.assertRaises(ExportError):
                create_selected_export(chats, root / "exports", ["../outside"])


if __name__ == "__main__":
    unittest.main()
