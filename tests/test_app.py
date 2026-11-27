import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from power_socket import app as app_module
from power_socket.app import (
    ConnectApp, ModelPickerScreen, ModelParametersPrompt, PopupMenu,
    ProfileMenu, ProviderConfigMenu, ProviderEndpointPrompt, SettingsMenu,
)
from power_socket.models import Profile
from power_socket.providers.base import Generation
from power_socket.storage import load_chat, save_profiles


class StubProvider:
    def __init__(self):
        self.messages = []

    def generate(self, model, messages, endpoint):
        self.messages = messages
        return Generation("stubbed response")


class StubSessionManager:
    def __init__(self):
        self.provider = StubProvider()

    def is_ready(self, provider, endpoint):
        return False

    def generate(self, provider, model, messages, endpoint, options=None):
        return self.provider.generate(model, messages, endpoint)

    def close(self):
        pass


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
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
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
                    self.assertIn("The user's name is Arkan.", app.provider_sessions.provider.messages[0]["content"])
                    self.assertIn("Preferred language: Indonesian.", app.provider_sessions.provider.messages[1]["content"])


    async def test_popup_navigation_opens_and_exposes_settings_and_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            chat_dir.mkdir()
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False, "memory.md")
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(40, 15)) as pilot:
                    await pilot.click("#menu-button")
                    self.assertIsInstance(app.screen, PopupMenu)
                    menu_items = app.screen.query_one("#menu-items", app_module.ListView)
                    self.assertIn("back", app.screen._item_actions.values())
                    app.screen.dismiss("settings")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, SettingsMenu)
                    app.screen.dismiss("profiles")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, ProfileMenu)
                    app.screen.dismiss("provider")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, ProviderConfigMenu)

    async def test_model_parameters_screen_is_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            chat_dir.mkdir()
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False, "memory.md")
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(80, 30)) as pilot:
                    app.push_screen(ModelParametersPrompt({}))
                    await pilot.pause()
                    self.assertIsInstance(app.screen, ModelParametersPrompt)
                    self.assertIsNotNone(app.screen.query_one("#temperature", app_module.Input))

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

    async def test_enter_sends_and_shift_enter_inserts_newline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            chat_dir.mkdir()
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False, "memory.md")
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(80, 30)) as pilot:
                    app._create_chat("keyboard-test")
                    composer = app.query_one("#composer", app_module.TextArea)
                    composer.focus()
                    composer.insert("first line")
                    await pilot.press("shift+enter")
                    composer.insert("second line")
                    self.assertEqual(composer.text, "first line\nsecond line")
                    with patch.object(app, "_send_message") as send:
                        await pilot.press("enter")
                        await pilot.pause()
                    send.assert_called_once_with("first line\nsecond line")
                    self.assertEqual(composer.text, "")

    async def test_profile_commands_live_under_settings_namespace(self):
        app = ConnectApp()
        async with app.run_test(size=(80, 24)):
            with patch.object(app, "_set_status") as set_status:
                app._handle_command("/profile change")
            set_status.assert_called_once_with("Profile commands moved. Use /settings profile ...")
            with patch.object(app, "_show_profile_picker") as show_picker:
                app._handle_command("/settings profile")
            show_picker.assert_called_once()

    async def test_profile_picker_uses_valid_ids_and_selects_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            chat_dir.mkdir()
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False, "memory.md"),
                Profile("Coding", "Dev", "ollama", "tiny", False, "memory2.md"),
            ])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(40, 15)) as pilot:
                    app._show_profile_picker()
                    await pilot.pause()
                    self.assertEqual(app.screen.query_one("#menu-item-0").id, "menu-item-0")
                    self.assertEqual(app.screen.query_one("#menu-item-1").id, "menu-item-1")
                    await pilot.click("#menu-item-1")
                    await pilot.pause()
                    self.assertEqual(app.active_profile.profilename, "Coding")

    async def test_new_chat_prompt_has_back_and_continue(self):
        app = ConnectApp()
        result = []
        async with app.run_test(size=(40, 15)) as pilot:
            app.push_screen(app_module.NewChatPrompt(), result.append)
            await pilot.pause()
            self.assertIsNotNone(app.screen.query_one("#back", app_module.Button))
            self.assertIsNotNone(app.screen.query_one("#continue", app_module.Button))
            app.screen.query_one("#new-name", app_module.Input).value = "mobile-chat"
            app.screen._continue()
            await pilot.pause()
        self.assertEqual(result, ["mobile-chat"])

    async def test_hierarchical_commands_manage_chats_and_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            memory_dir = root / "memory"
            chat_dir.mkdir()
            save_profiles(profile_file, [
                Profile("Default", "User", "ollama", "tiny", False, "memory.md"),
            ])
            (chat_dir / "session-one.jsonl").write_text("", encoding="utf-8")
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "MEMORY_DIR", memory_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(100, 30)):
                    app._handle_command('/chat open "session-one"')
                    self.assertEqual(app.active_chat, "session-one")
                    app._handle_command('/chat rename "session-one" "renamed chat"')
                    self.assertEqual(app.active_chat, "renamed chat")
                    self.assertTrue((chat_dir / "renamed chat.jsonl").exists())
                    app._handle_command('/settings profile create "Coding" "Dev User" ollama tiny "http://localhost:11434" true')
                    self.assertEqual(app.active_profile.profilename, "Coding")
                    self.assertTrue(app.active_profile.memory_enabled)
                    app._handle_command('/settings profile edit "Coding" model "qwen3:4b"')
                    self.assertEqual(app.active_profile.currentmodel, "qwen3:4b")
                    app._handle_command('/settings profile edit "Coding" username "Developer Two"')
                    self.assertEqual(app.active_profile.username, "Developer Two")
                    app._handle_command('/settings profile provider edit ollama "http://localhost:11434"')
                    self.assertEqual(app.active_profile.provider, "ollama")
                    app._handle_command('/settings profile change')
                    self.assertIsInstance(app.screen, PopupMenu)
                    app._handle_command('/chat delete "renamed chat"')
                    self.assertIsInstance(app.screen, app_module.ConfirmDeletePrompt)
                    app._delete_named_chat_result("renamed chat", True)
                    self.assertFalse((chat_dir / "renamed chat.jsonl").exists())

    async def test_model_and_provider_commands_and_parameter_buttons(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_file = root / "profiles.jsonl"
            chat_dir = root / "chats"
            chat_dir.mkdir()
            profile = Profile("Default", "User", "ollama", "old-model", False, "memory.md")
            save_profiles(profile_file, [profile])
            with (
                patch.object(app_module, "PROFILE_FILE", profile_file),
                patch.object(app_module, "CHAT_DIR", chat_dir),
                patch.object(app_module, "ProviderSessionManager", return_value=StubSessionManager()),
            ):
                app = ConnectApp()
                async with app.run_test(size=(90, 28)) as pilot:
                    app._handle_command("/settings profile provider current")
                    self.assertEqual(app.active_profile.provider, "ollama")
                    app._handle_command('/settings profile provider edit openai_compatible "http://localhost:8000/v1"')
                    self.assertEqual(app.active_profile.provider, "openai_compatible")
                    self.assertEqual(app.active_profile.endpoint, "http://localhost:8000/v1")
                    app._handle_command("/model current")
                    app._handle_command('/model change "qwen3:4b"')
                    self.assertEqual(app.active_profile.currentmodel, "qwen3:4b")
                    app._handle_command("/model edit 0.7 0.9 20 4096 512 true")
                    self.assertEqual(app.active_profile.model_parameters["top_k"], 20)
                    self.assertTrue(app.active_profile.model_parameters["thinking_mode"])
                    app.push_screen(ModelParametersPrompt(app.active_profile.model_parameters, app.active_profile.provider))
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#save", app_module.Button))
                    self.assertIsNotNone(app.screen.query_one("#cancel", app_module.Button))
                    self.assertIsNotNone(app.screen.query_one("#thinking-mode", app_module.Checkbox))
                    await pilot.click("#cancel")
                    await pilot.pause()

    async def test_general_and_shared_context_settings_are_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instructions = root / "instructions.jsonl"
            instructions.write_text('{"Instruction":"Be concise","act":"always"}\n', encoding="utf-8")
            memory = root / "memory.md"
            memory.write_text("# Shared memory\n", encoding="utf-8")
            skills = root / "skills"
            skills.mkdir()
            with patch.object(ConnectApp, "_context_settings_path", return_value=root / "context_settings.json"):
                app = ConnectApp()
                async with app.run_test(size=(100, 32)) as pilot:
                    app._handle_command("/settings context set instructions " + str(instructions))
                    await pilot.pause()
                    saved = json.loads((root / "context_settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["instructions"], str(instructions))
                    app._handle_command("/settings context set memory " + str(memory))
                    await pilot.pause()
                    saved = json.loads((root / "context_settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["memory"], str(memory))
                    app._handle_command("/settings context set skills " + str(skills))
                    await pilot.pause()
                    saved = json.loads((root / "context_settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["skills"], str(skills))
                    app._handle_command("/settings context show")
                    app.push_screen(app_module.GeneralSettingsMenu())
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#menu-items", app_module.ListView))
                    app.pop_screen()
                    app.push_screen(app_module.SharedResourcesPrompt("all", saved))
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#instructions", app_module.Input))
                    self.assertIsNotNone(app.screen.query_one("#memory", app_module.Input))
                    self.assertIsNotNone(app.screen.query_one("#skills", app_module.Input))

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
