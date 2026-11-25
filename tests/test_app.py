import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cavde_connect import app as app_module
from cavde_connect.app import ConnectApp, ModelPickerScreen
from cavde_connect.models import Profile
from cavde_connect.providers.base import Generation
from cavde_connect.storage import load_chat, save_profiles


class StubProvider:
    def __init__(self):
        self.messages = []

    def generate(self, model, messages, endpoint):
        self.messages = messages
        return Generation("stubbed response")


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_loads_profile_and_creates_shared_chat_and_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "data" / "chats"
            memory_dir = root / "data" / "memory"
            chat_dir.mkdir(parents=True)
            memory_dir.mkdir(parents=True)
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False,
                        "data/memory/default.md")
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
            ):
                app = ConnectApp()
                async with app.run_test(size=(110, 40)):
                    self.assertEqual(app.active_profile.profilename, "Default")
                    app._create_chat("shared-chat")
                    app._create_chat("current-chat")
                    self.assertEqual(app.active_chat, "current-chat")
                    app._create_profile_result({
                        "name": "Coding",
                        "username": "Developer",
                        "provider": "ollama",
                        "model": "tiny",
                        "endpoint": "http://127.0.0.1:11434",
                        "memory": True,
                    })
                    self.assertEqual(app.active_profile.profilename, "Coding")
                    self.assertEqual(app.active_chat, "current-chat")
                    self.assertTrue((memory_dir / "coding.md").exists())
                    app._edit_profile_result({
                        "username": "Coder",
                        "provider": "llamacpp",
                        "model": "coder-model",
                        "endpoint": "http://127.0.0.1:8080/v1",
                        "memory": True,
                    })
                    self.assertEqual(app.active_profile.username, "Coder")
                    self.assertEqual(app.active_profile.currentmodel, "coder-model")

    async def test_send_message_runs_in_worker_and_saves_jsonl(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "data" / "chats"
            memory_dir = root / "data" / "memory"
            chat_dir.mkdir(parents=True)
            memory_dir.mkdir(parents=True)
            (memory_dir / "default.md").write_text("Preferred language: Indonesian.", encoding="utf-8")
            save_profiles(profile_file, [
                Profile("Default", "Arkan", "ollama", "tiny", True,
                        "data/memory/default.md")
            ])
            provider = StubProvider()
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
                patch.object(app_module, "get_provider", return_value=provider),
            ):
                app = ConnectApp()
                async with app.run_test(size=(110, 40)) as pilot:
                    app._create_chat("worker-test")
                    app._send_message("hello")
                    for _ in range(20):
                        await pilot.pause(0.05)
                        if not app._busy:
                            break
                    self.assertFalse(app._busy)
                    self.assertEqual(
                        load_chat(chat_dir / "worker-test.jsonl"),
                        [{"input": "hello", "output": "stubbed response"}],
                    )
                    self.assertIn("The user's name is Arkan.", provider.messages[0]["content"])
                    self.assertIn("Preferred language: Indonesian.", provider.messages[1]["content"])


    async def test_profile_deletion_keeps_memory_file_and_shared_chats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "data" / "chats"
            memory_dir = root / "data" / "memory"
            chat_dir.mkdir(parents=True)
            memory_dir.mkdir(parents=True)
            retained_memory = memory_dir / "coding.md"
            retained_memory.write_text("keep this", encoding="utf-8")
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False,
                        "data/memory/default.md"),
                Profile("Coding", "Dev", "ollama", "tiny", True,
                        "data/memory/coding.md"),
            ])
            (chat_dir / "shared.jsonl").write_text("", encoding="utf-8")
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
            ):
                app = ConnectApp()
                async with app.run_test(size=(110, 40)):
                    app.active_profile = app.profiles[1]
                    app._delete_profile_result(True)
                    self.assertEqual(app.active_profile.profilename, "Default")
                    self.assertEqual([p.profilename for p in app.profiles], ["Default"])
                    self.assertTrue(retained_memory.exists())
                    self.assertTrue((chat_dir / "shared.jsonl").exists())

    async def test_memory_editor_opens_active_profile_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "data" / "chats"
            memory_dir = root / "data" / "memory"
            chat_dir.mkdir(parents=True)
            memory_dir.mkdir(parents=True)
            memory_file = memory_dir / "default.md"
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False,
                        "data/memory/default.md")
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
                patch.object(app_module.os, "startfile", create=True) as open_file,
            ):
                app = ConnectApp()
                async with app.run_test(size=(110, 40)):
                    with patch.object(app_module.sys, "platform", "win32"):
                        app.action_edit_memory()
                self.assertTrue(memory_file.exists())
                open_file.assert_called_once_with(str(memory_file))

    async def test_memory_editor_uses_native_openers_on_macos_and_linux(self):
        for platform, command in (("darwin", "open"), ("linux", "xdg-open")):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                profile_file = root / "profiles.jsonl"
                chat_dir = root / "data" / "chats"
                memory_dir = root / "data" / "memory"
                chat_dir.mkdir(parents=True)
                memory_dir.mkdir(parents=True)
                memory_file = memory_dir / "default.md"
                save_profiles(profile_file, [
                    Profile("Default", "User", "ollama", "tiny", False,
                            "data/memory/default.md")
                ])
                with (
                    patch.object(app_module, "PROFILE_FILE", profile_file),
                    patch.object(app_module, "CHAT_DIR", chat_dir),
                    patch.object(app_module, "MEMORY_DIR", memory_dir),
                ):
                    app = ConnectApp()
                    async with app.run_test(size=(110, 40)):
                        with (
                            patch.object(app_module.sys, "platform", platform),
                            patch.object(app_module.subprocess, "Popen") as open_process,
                        ):
                            app.action_edit_memory()
                        self.assertTrue(memory_file.exists())
                        open_process.assert_called_once_with([command, str(memory_file)])

    async def test_model_picker_uses_arrow_keys_and_enter(self):
        app = ConnectApp()
        chosen = []
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(ModelPickerScreen(["model-a", "model-b"]), chosen.append)
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
        self.assertEqual(chosen, ["model-b"])


if __name__ == "__main__":
    unittest.main()
