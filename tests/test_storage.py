import json
import tempfile
import unittest
from pathlib import Path

from power_socket.models import Profile
from power_socket.storage import (
    append_chat_turn, chat_path, delete_chat, load_chat, load_profiles,
    rename_chat, save_profiles, validate_chat_name,
)


class StorageTests(unittest.TestCase):
    def test_profiles_round_trip_jsonl(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.jsonl"
            save_profiles(path, [Profile("Default", "User", "ollama", "tiny", False,
                                         "data/memory/default.md", model_parameters={"temperature": 0.6})])
            loaded = load_profiles(path)
            self.assertEqual(loaded[0].profilename, "Default")
            self.assertFalse(loaded[0].memory_enabled)
            self.assertEqual(loaded[0].model_parameters, {"temperature": 0.6})
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_legacy_profile_without_model_parameters_loads_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.jsonl"
            path.write_text(json.dumps({
                "Profilename": "Legacy", "Username": "User", "provider": "ollama",
                "currentmodel": "tiny", "memory": [False, "memory.md"],
            }) + "\n", encoding="utf-8")
            loaded = load_profiles(path)
            self.assertEqual(loaded[0].model_parameters, {})

    def test_chat_format_is_cavde_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            path = chat_path(Path(temp), "test-chat")
            append_chat_turn(path, "hello", "hi")
            self.assertEqual(load_chat(path), [{"input": "hello", "output": "hi"}])
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(row), {"input", "output"})

    def test_profiles_name_is_hashed_as_reserved_name(self):
        result = validate_chat_name("profiles")
        self.assertNotEqual(result.casefold(), "profiles")
        self.assertTrue(result.startswith("blocked-"))
        self.assertEqual(len(result), 18)

    def test_names_are_safe(self):
        with self.assertRaises(ValueError):
            validate_chat_name("../outside")
        self.assertTrue(validate_chat_name("CON").startswith("blocked-"))

    def test_rename_and_delete_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            old = chat_path(folder, "before")
            append_chat_turn(old, "hello", "world")
            new_name = rename_chat(folder, "before", "after")
            self.assertEqual(new_name, "after")
            self.assertTrue((folder / "after.jsonl").exists())
            delete_chat(folder, "after")
            self.assertFalse((folder / "after.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
