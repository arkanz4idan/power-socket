from functools import partial
import os
import json
from pathlib import Path
import re
import subprocess
import sys
import shlex

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from .sessions import ProviderSessionManager
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, ListItem, ListView, RichLog,
    Static, TextArea,
)

from .config import CHAT_DIR, MEMORY_DIR, PROFILE_FILE
from .models import Profile
from .providers.base import ProviderError
from .providers.registry import get_provider
from .storage import (
    StorageError,
    append_chat_turn,
    chat_path,
    delete_chat,
    list_chats,
    load_chat,
    load_profiles,
    rename_chat,
    save_profiles,
)


class NewChatPrompt(ModalScreen[str | None]):
    CSS = """
    NewChatPrompt { align: center middle; }
    #dialog { width: 90%; max-width: 60; height: auto; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { margin-top: 1; }
    #dialog-buttons { height: 3; margin-top: 1;  }
    #dialog-buttons Button { width: 1fr; }
    #cancel { margin-right: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Back")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New conversation name")
            yield Input(placeholder="e.g. coding-session", id="new-name")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="back")
                yield Button("Continue", variant="primary", id="continue")

    def _continue(self) -> None:
        name = self.query_one("#new-name", Input).value.strip()
        if name:
            self.dismiss(name)
        else:
            self.app.notify("Enter a conversation name first.", severity="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue":
            self._continue()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._continue()

    def action_cancel(self) -> None:
        self.dismiss(None)


class RenameChatPrompt(ModalScreen[str | None]):
    CSS = """
    RenameChatPrompt { align: center middle; }
    #dialog { width: 60; height: 11; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { margin-top: 1; }
    #dialog Button { margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Rename chat: {self.current_name}")
            yield Input(value=self.current_name, id="new-name")
            yield Button("Rename", variant="primary", id="rename")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#new-name", Input).value if event.button.id == "rename" else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDeletePrompt(ModalScreen[bool]):
    CSS = """
    ConfirmDeletePrompt { align: center middle; }
    #dialog { width: 60; height: 9; border: round $error; background: $panel; padding: 1 2; }
    #dialog Button { margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, chat_name: str) -> None:
        super().__init__()
        self.chat_name = chat_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Delete '{self.chat_name}' permanently?")
            yield Label("This removes the local JSONL file.")
            yield Button("Delete chat", variant="error", id="delete")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ConfirmDeleteProfilePrompt(ModalScreen[bool]):
    CSS = """
    ConfirmDeleteProfilePrompt { align: center middle; }
    #dialog { width: 64; height: 11; border: round $error; background: $panel; padding: 1 2; }
    #dialog Button { margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, profile_name: str) -> None:
        super().__init__()
        self.profile_name = profile_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Delete profile '{self.profile_name}'?")
            yield Label("Its memory file will be kept; shared chats will not be deleted.")
            yield Button("Delete profile", variant="error", id="delete")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete")

    def action_cancel(self) -> None:
        self.dismiss(False)


class NewProfilePrompt(ModalScreen[dict | None]):
    CSS = """
    NewProfilePrompt { align: center middle; }
    #dialog { width: 76; height: 34; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { height: 3; margin-bottom: 0; }
    #dialog Button { height: 3; margin-top: 0; }
    #dialog .field-label { height: 1; color: $text-muted; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("CREATE PROFILE")
            yield Label("Profile name", classes="field-label")
            yield Input(placeholder="e.g. Coding", id="profile-name")
            yield Label("Username shown to the AI", classes="field-label")
            yield Input(placeholder="e.g. Developer", id="profile-user")
            yield Label("Provider", classes="field-label")
            yield Input(value="ollama", placeholder="ollama / llamacpp / openai_compatible", id="profile-provider")
            yield Label("Model name", classes="field-label")
            yield Input(value="llama3.2", placeholder="e.g. llama3.2", id="profile-model")
            yield Label("Provider endpoint", classes="field-label")
            yield Input(value="http://127.0.0.1:11434", placeholder="http://127.0.0.1:11434", id="profile-endpoint")
            yield Checkbox("Enable this profile's Markdown memory (optional)", value=False, id="profile-memory")
            yield Button("Create profile", variant="primary", id="create")
            yield Button("Back", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create":
            self.dismiss(None)
            return
        self.dismiss({
            "name": self.query_one("#profile-name", Input).value.strip(),
            "username": self.query_one("#profile-user", Input).value.strip(),
            "provider": self.query_one("#profile-provider", Input).value.strip(),
            "model": self.query_one("#profile-model", Input).value.strip(),
            "endpoint": self.query_one("#profile-endpoint", Input).value.strip(),
            "memory": self.query_one("#profile-memory", Checkbox).value,
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditProfilePrompt(ModalScreen[dict | None]):
    CSS = """
    EditProfilePrompt { align: center middle; }
    #dialog { width: 90%; max-width: 76; height: auto; max-height: 90%; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { height: 3; margin-bottom: 0; }
    #dialog Button { height: 3; margin-top: 0; }
    #dialog .field-label { height: 1; color: $text-muted; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        p = self.profile
        with Vertical(id="dialog"):
            yield Label(f"EDIT PROFILE: {p.profilename}")
            yield Label("Call name / Username", classes="field-label")
            yield Input(value=p.username, placeholder="Username shown to the AI", id="profile-user")
            yield Label("Provider", classes="field-label")
            yield Input(value=p.provider, placeholder="ollama / openai_compatible", id="profile-provider")
            yield Label("Model", classes="field-label")
            yield Input(value=p.currentmodel, placeholder="Model name", id="profile-model")
            yield Label("Provider endpoint", classes="field-label")
            yield Input(value=p.endpoint, placeholder="http://127.0.0.1:11434", id="profile-endpoint")
            yield Checkbox("Enable this profile's Markdown memory", value=p.memory_enabled, id="profile-memory")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="cancel")
                yield Button("Save changes", variant="primary", id="save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        self.dismiss({
            "username": self.query_one("#profile-user", Input).value.strip(),
            "provider": self.query_one("#profile-provider", Input).value.strip().lower(),
            "model": self.query_one("#profile-model", Input).value.strip(),
            "endpoint": self.query_one("#profile-endpoint", Input).value.strip(),
            "memory": self.query_one("#profile-memory", Checkbox).value,
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


class ModelPickerScreen(ModalScreen[str | None]):
    CSS = """
    ModelPickerScreen { align: center middle; }
    #dialog { width: 70; height: 22; border: round $primary; background: $panel; padding: 1 2; }
    #models { height: 1fr; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, models: list[str]) -> None:
        super().__init__()
        self.models = models

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Available models: use UP/DOWN, then Enter")
            yield ListView(*[ListItem(Label(name)) for name in self.models], id="models")
            yield Button("Cancel", id="cancel")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "models":
            index = event.list_view.index
            if index is not None and index < len(self.models):
                self.dismiss(self.models[index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class MessageComposer(TextArea):
    """Multiline composer: Enter sends, Shift+Enter inserts a newline."""

    BINDINGS = [
        Binding("enter", "send_message", "Send", priority=True),
        Binding("shift+enter", "insert_newline", "New line", priority=True),
    ]

    def action_send_message(self) -> None:
        prompt = self.text.strip()
        if prompt:
            self.text = ""
            if prompt.startswith("/"):
                self.app._handle_command(prompt)
            else:
                self.app._send_message(prompt)

    def action_insert_newline(self) -> None:
        self.insert("\n")


class ConnectApp(App):
    TITLE = "Power Socket"
    SUB_TITLE = "Universal AI terminal client"
    CSS = """
    Screen { layout: vertical; }
    #topbar { height: 3; padding: 0 1; }
    #chat-context { width: 1fr; content-align: right middle; color: $text-muted; }
    #workspace { width: 1fr; height: 1fr; padding: 0 1; }
    #chat-log { height: 1fr; border: round $surface; padding: 1; overflow-y: auto; }
    #empty-state { height: 1fr; content-align: center middle; }
    #composer-row { height: 5; }
    #composer { width: 1fr; height: 5; border: round $surface; }
    #status { height: 1; color: $text-muted; padding-left: 1; }
    ListView { height: 1fr; }
    """
    BINDINGS = [
        Binding("ctrl+o", "open_menu", "Menu"),
        Binding("ctrl+n", "new_chat", "New chat"),
        Binding("ctrl+m", "rename_chat", "Rename chat"),
        Binding("ctrl+d", "delete_chat", "Delete chat"),
        Binding("ctrl+shift+p", "new_profile", "New profile"),
        Binding("ctrl+shift+x", "delete_profile", "Delete profile"),
        Binding("ctrl+e", "edit_profile", "Edit profile"),
        Binding("ctrl+shift+m", "edit_memory", "Edit memory"),
        Binding("ctrl+l", "list_models", "List models"),
        Binding("ctrl+p", "open_menu", "Menu"),
        Binding("ctrl+r", "refresh_chats", "Refresh"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.profiles: list[Profile] = []
        self.active_profile: Profile | None = None
        self.active_chat = ""
        self.history: list[dict[str, str]] = []
        self._busy = False
        self._profile_names: list[str] = []
        self._chat_names: list[str] = []
        self.provider_sessions = ProviderSessionManager()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="topbar"):
            yield Button("☰ Menu", id="menu-button", variant="default")
            yield Label("Current Chat: (none)", id="chat-context")
        with Vertical(id="workspace"):
            yield Static(
                Align.center(Panel(
                    Text("Start a conversation\nEnter sends | Shift+Enter adds a line\nUse /help for commands.", justify="center"),
                    title="POWER SOCKET", border_style="blue", padding=(1, 2)
                )),
                id="empty-state",
            )
            yield RichLog(id="chat-log", wrap=True, markup=False, auto_scroll=True)
            with Horizontal(id="composer-row"):
                yield MessageComposer(id="composer", placeholder="Message or /command...", soft_wrap=True, show_line_numbers=False)
            yield Label("Starting...", id="status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "menu-button":
            self.action_open_menu()

    def action_open_menu(self) -> None:
        self.push_screen(PopupMenu([("chat_menu", "Chat"), ("settings", "Settings"), ("back", "Back")]), self._menu_selected)

    def _menu_selected(self, action):
        if action == "chat_menu":
            items = [("new", "New conversation"), ("open", "Open conversation"), ("rename", "Rename current chat"), ("delete", "Delete current chat"), ("refresh", "Refresh conversations"), ("back", "Back")]
            self.push_screen(PopupMenu(items), self._chat_menu_selected)
        elif action == "settings":
            self.push_screen(SettingsMenu(), self._settings_selected)
        elif action == "back":
            self.query_one("#composer", TextArea).focus()

    def _chat_menu_selected(self, action):
        if action == "new": self.action_new_chat()
        elif action == "open": self._show_chat_picker()
        elif action == "rename": self.action_rename_chat()
        elif action == "delete": self.action_delete_chat()
        elif action == "refresh": self.action_refresh_chats()
        elif action == "back": self.action_open_menu()

    def _settings_selected(self, action):
        if action == "profiles": self.push_screen(ProfileMenu(), self._profile_menu_selected)
        elif action == "memory": self.push_screen(SharedResourcesPrompt("memory", self._load_context_settings()), self._save_shared_resource)
        elif action == "general": self.push_screen(GeneralSettingsMenu(), self._general_settings_selected)
        elif action == "back": self.action_open_menu()

    def _general_settings_selected(self, action):
        if action == "export":
            try:
                path = Path(__file__).resolve().parent.parent / "settings.json"
                from .exporter import load_export_settings
                settings = load_export_settings(path)
                self.push_screen(ExportSettingsPrompt(settings), self._save_export_settings)
            except Exception as exc:
                self._set_status(f"Cannot load export settings: {exc}")
        elif action == "context":
            self.push_screen(SharedResourcesPrompt("all", self._load_context_settings()), self._save_shared_resource)
        elif action == "back":
            self.push_screen(SettingsMenu(), self._settings_selected)

    def _save_export_settings(self, settings):
        if settings is None:
            return
        path = Path(__file__).resolve().parent.parent / "settings.json"
        try:
            from .settings_cli import _save_settings
            _save_settings(path, settings)
            self._set_status("General settings saved.")
        except Exception as exc:
            self._set_status(f"Could not save general settings: {exc}")

    def _context_settings_path(self):
        return Path(__file__).resolve().parent.parent / "context_settings.json"

    def _load_context_settings(self):
        path = self._context_settings_path()
        defaults = {"instructions": "", "memory": "", "skills": ""}
        try:
            if not path.exists():
                return defaults
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("context_settings.json must be an object")
            for key in defaults:
                value = data.get(key, "")
                if not isinstance(value, str):
                    raise ValueError(f"{key} path must be a string")
                defaults[key] = value
            return defaults
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._set_status(f"Cannot read shared resource settings: {exc}")
            return defaults

    def _save_shared_resource(self, values):
        if values is None:
            return
        skill_warnings = []
        for key, value in values.items():
            if value:
                path = Path(value).expanduser()
                expected_file = key in {"instructions", "memory"}
                if not path.exists() or (expected_file and not path.is_file()) or (key == "skills" and not path.is_dir()):
                    self._set_status(f"Invalid {key} path. Select an existing {'file' if expected_file else 'folder'}.")
                    return
                if key == "instructions" and path.suffix.lower() != ".jsonl":
                    self._set_status("Instructions must be a .jsonl file.")
                    return
                if key == "memory" and path.suffix.lower() != ".md":
                    self._set_status("Memory must be a .md file.")
                    return
                try:
                    if key == "instructions":
                        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                            if not line.strip():
                                continue
                            item = json.loads(line)
                            if not isinstance(item, dict) or "Instruction" not in item or "act" not in item:
                                raise ValueError(f"Instructions line {line_number} must be an object with Instruction and act fields.")
                    elif key == "memory":
                        path.read_text(encoding="utf-8")
                    elif key == "skills":
                        entries = list(path.iterdir())
                        incomplete = [entry.name for entry in entries if entry.is_dir() and not (entry / "SKILL.md").is_file()]
                        if incomplete:
                            skill_warnings = incomplete[:8]
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                    self._set_status(f"Cannot validate {key}: {exc}")
                    return
        try:
            target = self._context_settings_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(target)
            message = "Shared resource paths saved. Original files were not copied."
            if skill_warnings:
                message += " Incomplete skill folders (missing SKILL.md): " + ", ".join(skill_warnings)
            self._set_status(message)
        except OSError as exc:
            self._set_status(f"Could not save shared resource paths: {exc}")

    def _profile_menu_selected(self, action):
        if action == "select": self._show_profile_picker()
        elif action == "create": self.action_new_profile()
        elif action == "edit": self.action_edit_profile()
        elif action == "delete": self.action_delete_profile()
        elif action == "provider": self.push_screen(ProviderConfigMenu(), self._provider_config_selected)
        elif action == "back": self.push_screen(SettingsMenu(), self._settings_selected)

    def _provider_config_selected(self, action):
        if action == "provider":
            if self.active_profile:
                self.push_screen(ProviderEndpointPrompt(self.active_profile), self._apply_provider_endpoint)
        elif action == "model": self.action_list_models()
        elif action == "parameters":
            if self.active_profile:
                self.push_screen(ModelParametersPrompt(self.active_profile.model_parameters, self.active_profile.provider), self._apply_model_parameters)
        elif action == "back": self.push_screen(ProfileMenu(), self._profile_menu_selected)

    def _apply_model_parameters(self, values):
        if values is None or self.active_profile is None: return
        previous = self.active_profile.model_parameters
        self.active_profile.model_parameters = values
        try: save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            self.active_profile.model_parameters = previous
            self._set_status(f"Could not save model parameters: {exc}")
            return
        self._set_status("Model parameters saved.")

    def _show_profile_picker(self):
        if not self.profiles:
            self._set_status("No profiles are available.")
            return
        items = [(str(i), p.profilename) for i, p in enumerate(self.profiles)]
        self.push_screen(PopupMenu(items), self._profile_selected)

    def _profile_selected(self, selected):
        if selected is None: return
        try:
            self.active_profile = self.profiles[int(selected)]
            self._render_chats()
            self._set_status(self._profile_status())
        except (ValueError, IndexError): self._set_status("Invalid profile selection.")

    def _show_chat_picker(self):
        self._chat_names = list_chats(CHAT_DIR)
        if not self._chat_names:
            self._set_status("No saved chats. Create a new chat first.")
            return
        self.push_screen(PopupMenu([(name, name) for name in self._chat_names]), self._chat_selected)

    def _chat_selected(self, selected):
        if selected:
            self.active_chat = selected
            self._load_active_chat()
            self._set_status(f"Opened chat: {selected}")

    def _update_chat_context(self):
        self.query_one("#chat-context", Label).update(f"Current Chat: {self.active_chat or '(none)'}")

    def on_mount(self) -> None:
        self._load_initial_data()

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)

    def _load_initial_data(self) -> None:
        try:
            self.profiles = load_profiles(PROFILE_FILE)
            if not self.profiles:
                self._set_status("No profiles found. Add one to profiles.jsonl.")
                return
            self.active_profile = self.profiles[0]
            self._render_chats()
            self._update_chat_context()
            self._set_status(self._profile_status())
        except (StorageError, OSError) as exc:
            self._set_status(f"Storage error: {exc}")

    def _profile_status(self) -> str:
        if self.active_profile is None:
            return "No active profile."
        p = self.active_profile
        return (
            f"Profile: {p.profilename} | Provider: {p.provider} | "
            f"Model: {p.currentmodel} | Memory: {'ON' if p.memory_enabled else 'OFF'}"
        )

    def _render_profiles(self) -> None:
        self._profile_names = [profile.profilename for profile in self.profiles]

    def _render_chats(self) -> None:
        self._chat_names = list_chats(CHAT_DIR)
        if self.active_chat and self.active_chat in self._chat_names:
            self._load_active_chat()
        elif self._chat_names and not self.active_chat:
            self.active_chat = self._chat_names[0]
            self._load_active_chat()
        elif not self._chat_names:
            self.active_chat = ""
            self.history = []
            self._render_log()
        self._update_chat_context()

    def _load_active_chat(self) -> None:
        if not self.active_chat:
            self.history = []
            self._render_log()
            return
        try:
            self.history = load_chat(chat_path(CHAT_DIR, self.active_chat))
            self._render_log()
        except (StorageError, ValueError) as exc:
            self._set_status(str(exc))

    def _render_log(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        if not self.history:
            self.query_one("#empty-state", Static).display = True
            log.display = False
        else:
            self.query_one("#empty-state", Static).display = False
            log.display = True
        for turn in self.history:
            user_line = Text()
            user_line.append("You: ", style="bold cyan")
            user_line.append(turn["input"])
            log.write(user_line)
            assistant_line = Text()
            assistant_line.append("Assistant: ", style="bold green")
            assistant_line.append(turn["output"])
            log.write(assistant_line)
            log.write("")
        log.scroll_end(animate=False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "profiles":
            index = event.list_view.index
            if index is not None and index < len(self.profiles):
                self.active_profile = self.profiles[index]
                self._render_profiles()
                self._render_chats()
                self._set_status(self._profile_status())
        elif event.list_view.id == "chats":
            index = event.list_view.index
            if index is not None and index < len(self._chat_names):
                self.active_chat = self._chat_names[index]
                self._load_active_chat()
                self._set_status(f"Opened chat: {self.active_chat}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "composer":
            return
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""
        self._send_message(prompt)

    def _handle_command(self, raw_command: str) -> None:
        """Parse local slash commands; commands are never sent to the provider."""
        try:
            lexer = shlex.shlex(raw_command, posix=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            lexer.escape = ""
            parts = list(lexer)
        except ValueError as exc:
            self._set_status(f"Command syntax error: {exc}")
            return
        if not parts:
            return
        root, *args = parts
        root = root.lower()
        if root in {"/help", "/?"}:
            self.notify(
                "/chat new <name>\n"
                "/chat rename <new name>  (current chat)\n"
                "/chat rename <old name> <new name>\n"
                "/chat delete <name>\n"
                "/chat open <name>\n"
                "/chat refresh\n"
                "/settings profile create <name> <username> <provider> <model> <endpoint> [memory bool]\n"
                "/settings profile change\n"
                "/settings profile edit <name> <field> <value>\n"
                "/settings profile delete [name]\n"
                "/settings profile provider current | /settings profile provider edit <provider> <endpoint>\n"
                "/model current | /model change <model name>\n"
                "/model edit <temperature> <top_p> <top_k> <context_length> <max_tokens> [thinking]\n"
                "/settings general | /settings general export | /settings memory\n"
                "/settings export status|enable|disable\n"
                "/settings context show | /settings context set <instructions|memory|skills> <path>\n"
                "/models | /menu | /status | /quit",
                title="Power Socket command reference", timeout=20,
            )
        elif root == "/chat":
            self._handle_chat_command(args)
        elif root == "/profile":
            self._set_status("Profile commands moved. Use /settings profile ...")
        elif root == "/settings":
            self._handle_settings_command(args)
        elif root == "/model":
            self._handle_model_command(args)
        elif root == "/models":
            self.action_list_models()
        elif root == "/menu":
            self.action_open_menu()
        elif root == "/status":
            self._set_status(f"{self._profile_status()} | Chat: {self.active_chat or 'none'}")
        elif root in {"/quit", "/exit"}:
            self.exit()
        else:
            self._set_status(f"Unknown command: {root}. Type /help for commands.")

    def _handle_chat_command(self, args: list[str]) -> None:
        if not args:
            self._set_status("Usage: /chat <new|rename|delete|open|refresh>")
            return
        action, *values = args
        action = action.lower()
        try:
            if action == "new" and len(values) == 1:
                self._create_chat(values[0])
            elif action == "new" and not values:
                self.action_new_chat()
            elif action == "rename" and len(values) == 1:
                if not self.active_chat:
                    raise ValueError("No active chat. Use /chat rename <old> <new>.")
                self._rename_chat_by_name(self.active_chat, values[0])
            elif action == "rename" and len(values) == 2:
                self._rename_chat_by_name(values[0], values[1])
            elif action == "delete" and len(values) == 1:
                target = values[0]
                if not chat_path(CHAT_DIR, target).is_file():
                    raise FileNotFoundError(f"Chat not found: {target}")
                self.push_screen(ConfirmDeletePrompt(target),
                                 lambda confirmed, name=target: self._delete_named_chat_result(name, confirmed))
            elif action == "delete" and not values:
                if not self.active_chat:
                    raise ValueError("Usage: /chat delete <name>")
                self.action_delete_chat()
            elif action == "open" and len(values) == 1:
                match = next((n for n in list_chats(CHAT_DIR) if n.casefold() == values[0].casefold()), None)
                if match is None:
                    raise FileNotFoundError(f"Chat not found: {values[0]}")
                self._chat_selected(match)
            elif action == "open" and not values:
                self._show_chat_picker()
            elif action == "refresh" and not values:
                self.action_refresh_chats()
            else:
                self._set_status("Usage: /chat new <name> | rename <new> | rename <old> <new> | delete <name> | open <name> | refresh")
        except (ValueError, OSError, StorageError) as exc:
            self._set_status(str(exc))

    def _rename_chat_by_name(self, old_name: str, new_name: str) -> None:
        renamed = rename_chat(CHAT_DIR, old_name, new_name)
        if self.active_chat.casefold() == old_name.casefold():
            self.active_chat = renamed
            self._load_active_chat()
        self._render_chats()
        self._set_status(f"Renamed chat: {old_name} -> {renamed}")

    def _delete_named_chat_result(self, name: str, confirmed: bool) -> None:
        if not confirmed:
            return
        try:
            delete_chat(CHAT_DIR, name)
            if self.active_chat.casefold() == name.casefold():
                self.active_chat, self.history = "", []
            self._render_chats()
            self._render_log()
            self._set_status(f"Deleted chat: {name}")
        except (ValueError, OSError, StorageError) as exc:
            self._set_status(str(exc))

    def _handle_profile_command(self, args: list[str]) -> None:
        if not args:
            self._show_profile_picker()
            return
        action, *values = args
        action = action.lower()
        if action == "change" and not values:
            self._show_profile_picker()
        elif action == "create" and 5 <= len(values) <= 6:
            name, username, provider, model, endpoint = values[:5]
            if len(values) == 6 and values[5].lower() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                self._set_status("Memory must be true or false.")
                return
            memory = values[5].lower() in {"true", "1", "yes", "on"} if len(values) == 6 else False
            self._create_profile_from_values({
                "name": name, "username": username, "provider": provider,
                "model": model, "endpoint": endpoint, "memory": memory,
            })
        elif action == "edit" and len(values) >= 3:
            self._edit_profile_field(values[0], values[1], " ".join(values[2:]))
        elif action == "delete" and len(values) <= 1:
            profile = self._find_profile(values[0]) if values else self.active_profile
            if profile is None:
                self._set_status("Profile not found or no active profile.")
            elif len(self.profiles) <= 1:
                self._set_status("The last profile cannot be deleted.")
            else:
                self.push_screen(
                    ConfirmDeleteProfilePrompt(profile.profilename),
                    lambda confirmed, target=profile: self._delete_named_profile_result(target, confirmed),
                )
        elif action == "provider" and (not values or values == ["current"]):
            profile = self.active_profile
            if profile is None:
                self._set_status("No active profile.")
            else:
                self._set_status(f"Provider: {profile.provider} | Endpoint: {profile.endpoint}")
        elif action == "provider" and len(values) >= 3 and values[0].lower() == "edit":
            self._save_provider_config(values[1], " ".join(values[2:]))
        else:
            self._set_status("Usage: /settings profile create <name> <username> <provider> <model> <endpoint> [true|false] | change | edit <name> <field> <value> | delete [name] | provider current|edit <provider> <endpoint>")

    def _handle_settings_command(self, args: list[str]) -> None:
        if not args or args[0].lower() == "general" and len(args) == 1:
            self.push_screen(GeneralSettingsMenu(), self._general_settings_selected)
            return
        if args[0].lower() == "profile":
            self._handle_profile_command(args[1:])
            return
        if args[0].lower() == "memory" and len(args) == 1:
            self.push_screen(SharedResourcesPrompt("memory", self._load_context_settings()), self._save_shared_resource)
            return
        if args[0].lower() == "general" and len(args) == 2 and args[1].lower() == "export":
            try:
                from .exporter import load_export_settings
                settings = load_export_settings(Path(__file__).resolve().parent.parent / "settings.json")
                self.push_screen(ExportSettingsPrompt(settings), self._save_export_settings)
            except Exception as exc:
                self._set_status(f"Cannot load export settings: {exc}")
            return
        area, *values = args
        if area.lower() == "export":
            if len(values) != 1 or values[0].lower() not in {"status", "enable", "disable"}:
                self._set_status("Usage: /settings export status|enable|disable")
                return
            try:
                from .exporter import load_export_settings
                from .settings_cli import _save_settings
                path = Path(__file__).resolve().parent.parent / "settings.json"
                settings = load_export_settings(path)
                if values[0].lower() == "status":
                    self._set_status(f"Dataset export: {'ENABLED' if settings['dataset_export_enabled'] else 'DISABLED'} | Selected chats: {len(settings['selected_chats'])} | Folders: {len(settings['selected_folders'])}")
                    return
                settings["dataset_export_enabled"] = values[0].lower() == "enable"
                _save_settings(path, settings)
                self._set_status(f"Dataset export {'enabled' if settings['dataset_export_enabled'] else 'disabled'}.")
            except Exception as exc:
                self._set_status(f"Export settings error: {exc}")
        elif area.lower() == "context":
            if values == ["show"]:
                cfg = self._load_context_settings()
                self._set_status("Instructions: " + (cfg["instructions"] or "(not selected)") + " | Memory: " + (cfg["memory"] or "(not selected)") + " | Skills: " + (cfg["skills"] or "(not selected)"))
            elif len(values) >= 3 and values[0].lower() == "set" and values[1].lower() in {"instructions", "memory", "skills"}:
                cfg = self._load_context_settings()
                cfg[values[1].lower()] = " ".join(values[2:])
                self._save_shared_resource(cfg)
            else:
                self._set_status("Usage: /settings context show | /settings context set <instructions|memory|skills> <path>")
        else:
            self._set_status("Usage: /settings profile ... | /settings general | /settings export status|enable|disable | /settings context ...")

    def _save_provider_config(self, provider: str, endpoint: str) -> None:
        profile = self.active_profile
        if profile is None:
            self._set_status("No active profile.")
            return
        if not provider.strip() or not endpoint.strip():
            self._set_status("Provider and endpoint cannot be empty.")
            return
        previous = profile.provider, profile.endpoint
        profile.provider, profile.endpoint = provider.strip().lower(), endpoint.strip()
        try:
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            profile.provider, profile.endpoint = previous
            self._set_status(f"Could not save provider configuration: {exc}")
            return
        self._set_status(f"Provider configuration updated: {profile.provider} | {profile.endpoint}")

    def _handle_model_command(self, args: list[str]) -> None:
        if not args or args[0].lower() == "current" and len(args) == 1:
            profile = self.active_profile
            if profile is None:
                self._set_status("No active profile.")
            else:
                self._set_status(f"Model: {profile.currentmodel}")
            return
        action, *values = args
        if action.lower() == "change" and len(values) == 1:
            self._set_model_name(values[0])
        elif action.lower() == "edit" and len(values) in {5, 6}:
            keys = ("temperature", "top_p", "top_k", "context_length", "max_tokens")
            try:
                params = {}
                for key, raw in zip(keys, values[:5]):
                    if raw.lower() in {"none", "null", "-"}:
                        continue
                    value = float(raw) if key in {"temperature", "top_p"} else int(raw)
                    if value < 0:
                        raise ValueError(f"{key} cannot be negative")
                    if key == "top_p" and value > 1:
                        raise ValueError("top_p must be between 0 and 1")
                    params[key] = value
                if len(values) == 6:
                    mode = values[5].lower()
                    if mode not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                        raise ValueError("Thinking mode must be true or false.")
                    params["thinking_mode"] = mode in {"true", "1", "yes", "on"}
                else:
                    params["thinking_mode"] = False
                self._save_model_parameters(params)
            except ValueError as exc:
                self._set_status(f"Invalid model parameters: {exc}")
        else:
            self._set_status("Usage: /model current | /model change <model name> | /model edit <temperature> <top_p> <top_k> <context_length> <max_tokens> [thinking]")

    def _set_model_name(self, model: str) -> None:
        profile = self.active_profile
        if profile is None:
            self._set_status("No active profile.")
            return
        if not model.strip():
            self._set_status("Model name cannot be empty.")
            return
        previous = profile.currentmodel
        profile.currentmodel = model.strip()
        try:
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            profile.currentmodel = previous
            self._set_status(f"Could not save model: {exc}")
            return
        self._set_status(f"Current model: {profile.currentmodel}")

    def _save_model_parameters(self, params: dict) -> None:
        profile = self.active_profile
        if profile is None:
            self._set_status("No active profile.")
            return
        previous = profile.model_parameters
        profile.model_parameters = params
        try:
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            profile.model_parameters = previous
            self._set_status(f"Could not save model parameters: {exc}")
            return
        self._set_status("Model parameters saved.")

    def _find_profile(self, name: str) -> Profile | None:
        return next((p for p in self.profiles if p.profilename.casefold() == name.casefold()), None)

    def _create_profile_from_values(self, values: dict) -> None:
        name = values["name"].strip()
        if not all((name, values["username"], values["provider"], values["model"], values["endpoint"])):
            self._set_status("Profile name, username, provider, model, and endpoint are required.")
            return
        if self._find_profile(name):
            self._set_status(f"Profile already exists: {name}")
            return
        if not re.fullmatch(r"[\w .()-]{1,48}", name, flags=re.UNICODE):
            self._set_status("Profile name contains unsupported characters.")
            return
        memory_file = MEMORY_DIR / (re.sub(r"[^\w.-]", "_", name.lower()) + ".md")
        profile = Profile(name, values["username"], values["provider"].lower(), values["model"],
                          values["memory"], memory_file.relative_to(PROFILE_FILE.parent).as_posix(),
                          endpoint=values["endpoint"])
        try:
            if profile.memory_enabled:
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                memory_file.touch(exist_ok=True)
            self.profiles.append(profile)
            save_profiles(PROFILE_FILE, self.profiles)
            self.active_profile = profile
            self._render_profiles()
            self._render_chats()
            self._set_status(f"Created profile: {name}")
        except (StorageError, OSError, ValueError) as exc:
            self.profiles = [p for p in self.profiles if p is not profile]
            self._set_status(f"Could not create profile: {exc}")

    def _edit_profile_field(self, name: str, field: str, value: str) -> None:
        profile = self._find_profile(name)
        field = {"callname": "username", "user": "username", "model": "currentmodel",
                 "provider_endpoint": "endpoint", "memory": "memory_enabled"}.get(
                     field.lower().replace("-", "_"), field.lower().replace("-", "_"))
        allowed = {"username", "provider", "currentmodel", "endpoint", "memory_enabled"}
        if profile is None:
            self._set_status(f"Profile not found: {name}")
            return
        if field not in allowed:
            self._set_status("Editable fields: username, provider, model, endpoint, memory")
            return
        if field == "memory_enabled":
            if value.lower() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                self._set_status("Memory value must be true or false.")
                return
            new_value = value.lower() in {"true", "1", "yes", "on"}
        else:
            if not value.strip():
                self._set_status("Profile field cannot be empty.")
                return
            new_value = value.strip().lower() if field == "provider" else value.strip()
        previous = getattr(profile, field)
        setattr(profile, field, new_value)
        try:
            if field == "memory_enabled" and new_value:
                memory_file = Path(profile.memory_path)
                if not memory_file.is_absolute():
                    memory_file = PROFILE_FILE.parent / memory_file
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                memory_file.touch(exist_ok=True)
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError, ValueError) as exc:
            setattr(profile, field, previous)
            self._set_status(f"Could not update profile: {exc}")
            return
        self._set_status(f"Updated profile {name}: {field}")

    def _delete_named_profile_result(self, profile: Profile, confirmed: bool) -> None:
        if not confirmed:
            return
        if profile not in self.profiles:
            self._set_status("Profile no longer exists.")
            return
        if len(self.profiles) <= 1:
            self._set_status("The last profile cannot be deleted.")
            return
        remaining = [p for p in self.profiles if p is not profile]
        try:
            save_profiles(PROFILE_FILE, remaining)
        except (StorageError, OSError) as exc:
            self._set_status(f"Could not delete profile: {exc}")
            return
        self.profiles = remaining
        if self.active_profile is profile:
            self.active_profile = remaining[0]
            self._render_chats()
        self._render_profiles()
        self._set_status(f"Deleted profile: {profile.profilename}. Its memory file was retained.")

    def _delete_profile_by_name(self, name: str) -> None:
        profile = self._find_profile(name)
        if profile is None:
            self._set_status(f"Profile not found: {name}")
            return
        if len(self.profiles) <= 1:
            self._set_status("The last profile cannot be deleted.")
            return
        remaining = [p for p in self.profiles if p is not profile]
        try:
            save_profiles(PROFILE_FILE, remaining)
        except (StorageError, OSError) as exc:
            self._set_status(f"Could not delete profile: {exc}")
            return
        self.profiles = remaining
        if self.active_profile is profile:
            self.active_profile = remaining[0]
            self._render_chats()
        self._render_profiles()
        self._set_status(f"Deleted profile: {name}. Its memory file was retained.")

    def _apply_provider_endpoint(self, values: dict | None) -> None:
        if values is None:
            return
        profile = values.pop("profile")
        previous = profile.provider, profile.endpoint
        profile.provider = values["provider"].strip().lower()
        profile.endpoint = values["endpoint"].strip()
        if not profile.provider or not profile.endpoint:
            profile.provider, profile.endpoint = previous
            self._set_status("Provider and endpoint cannot be empty.")
            return
        try:
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            profile.provider, profile.endpoint = previous
            self._set_status(f"Could not save provider configuration: {exc}")
            return
        self._set_status(f"Provider configuration saved for {profile.profilename}.")

    def _send_message(self, prompt: str) -> None:
        profile = self.active_profile
        if self._busy:
            self._set_status("Please wait for the current response to finish.")
            return
        if profile is None:
            self._set_status("No active profile.")
            return
        if not self.active_chat:
            self._set_status("Create or select a chat first (Ctrl+N).")
            return
        messages: list[dict[str, str]] = []
        if profile.username.strip():
            messages.append({
                "role": "system",
                "content": f"The user's name is {profile.username}.",
            })
        if profile.memory_enabled:
            memory_file = Path(profile.memory_path)
            if not memory_file.is_absolute():
                memory_file = PROFILE_FILE.parent / memory_file
            if memory_file.exists():
                try:
                    with memory_file.open("r", encoding="utf-8") as handle:
                        memory_text = handle.read(64 * 1024)
                    if memory_text.strip():
                        messages.append({"role": "system", "content": "User memory:\n" + memory_text})
                except OSError as exc:
                    self._set_status(f"Memory could not be read: {exc}")
                    return
        for turn in self.history[-20:]:
            messages.append({"role": "user", "content": turn["input"]})
            messages.append({"role": "assistant", "content": turn["output"]})
        messages.append({"role": "user", "content": prompt})
        self._busy = True
        connecting = not self.provider_sessions.is_ready(profile.provider, profile.endpoint)
        self._set_status(
            "Connecting to provider..." if connecting else "Using active provider session..."
        )
        self.run_worker(
            partial(self._generate_and_store, profile, self.active_chat, prompt, messages),
            exclusive=True,
            thread=True,
        )

    def _generate_and_store(self, profile: Profile, chat_name: str,
                            prompt: str, messages: list[dict[str, str]]) -> None:
        try:
            response = self.provider_sessions.generate(
                profile.provider, profile.currentmodel, messages, profile.endpoint,
                options=profile.model_parameters,
            )
            append_chat_turn(chat_path(CHAT_DIR, chat_name), prompt, response.text)
            self.call_from_thread(self._after_response, chat_name, prompt, response.text)
        except (ProviderError, ValueError, StorageError, OSError) as exc:
            self.provider_sessions.invalidate(profile.provider, profile.endpoint)
            self.call_from_thread(self._finish_with_error, str(exc))

    def _finish_with_error(self, message: str) -> None:
        self._busy = False
        self._set_status(f"Error: {message}")

    def _after_response(self, chat_name: str, prompt: str, response: str) -> None:
        self._busy = False
        if chat_name != self.active_chat:
            self._set_status(f"Response saved in {chat_name}.")
            return
        self.history.append({"input": prompt, "output": response})
        self._render_log()
        self._set_status("Ready.")

    def action_new_chat(self) -> None:
        self.push_screen(NewChatPrompt(), self._create_chat)

    def _create_chat(self, name: str | None) -> None:
        if not name:
            return
        try:
            path = chat_path(CHAT_DIR, name)
            if path.exists():
                self._set_status("That chat already exists.")
                return
            path.touch()
            self.active_chat = path.stem
            self.history = []
            self._render_chats()
            self._render_log()
            self._set_status(f"Created chat: {self.active_chat}")
            self.query_one("#composer", TextArea).focus()
        except (ValueError, OSError) as exc:
            self._set_status(str(exc))

    def action_rename_chat(self) -> None:
        if not self.active_chat:
            self._set_status("Select a chat first.")
            return
        self.push_screen(RenameChatPrompt(self.active_chat), self._rename_chat_result)

    def _rename_chat_result(self, new_name: str | None) -> None:
        if not new_name:
            return
        try:
            self.active_chat = rename_chat(CHAT_DIR, self.active_chat, new_name)
            self._render_chats()
            self._set_status(f"Renamed chat to {self.active_chat}")
        except (ValueError, OSError) as exc:
            self._set_status(str(exc))

    def action_delete_chat(self) -> None:
        if not self.active_chat:
            self._set_status("Select a chat first.")
            return
        self.push_screen(ConfirmDeletePrompt(self.active_chat), self._delete_chat_result)

    def _delete_chat_result(self, confirmed: bool) -> None:
        if not confirmed:
            return
        deleted = self.active_chat
        try:
            delete_chat(CHAT_DIR, deleted)
            self.active_chat = ""
            self.history = []
            self._render_chats()
            self._render_log()
            self._set_status(f"Deleted chat: {deleted}")
        except (ValueError, OSError) as exc:
            self._set_status(str(exc))

    def action_new_profile(self) -> None:
        self.push_screen(NewProfilePrompt(), self._create_profile_result)

    def _create_profile_result(self, values: dict | None) -> None:
        if not values:
            return
        name = values["name"]
        username = values["username"]
        provider = values["provider"].lower()
        model = values["model"]
        endpoint = values["endpoint"]
        if not all((name, username, provider, model, endpoint)):
            self._set_status("All profile fields except memory checkbox are required.")
            return
        if any(p.profilename.casefold() == name.casefold() for p in self.profiles):
            self._set_status("A profile with that name already exists.")
            return
        if not re.fullmatch(r"[\w .()-]{1,48}", name, flags=re.UNICODE):
            self._set_status("Profile name contains unsupported characters.")
            return
        memory_file = MEMORY_DIR / (re.sub(r"[^\w.-]", "_", name.lower()) + ".md")
        profile = Profile(
            profilename=name,
            username=username,
            provider=provider,
            currentmodel=model,
            memory_enabled=values["memory"],
            memory_path=memory_file.relative_to(PROFILE_FILE.parent).as_posix(),
            endpoint=endpoint,
        )
        try:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            memory_file.touch(exist_ok=True)
            self.profiles.append(profile)
            save_profiles(PROFILE_FILE, self.profiles)
            self.active_profile = profile
            self._render_profiles()
            self._render_chats()
            self._set_status(f"Created profile: {name}")
        except (StorageError, OSError, ValueError) as exc:
            self._set_status(f"Could not create profile: {exc}")

    def action_edit_profile(self) -> None:
        if self.active_profile is None:
            self._set_status("No active profile.")
            return
        self.push_screen(EditProfilePrompt(self.active_profile), self._edit_profile_result)

    def _edit_profile_result(self, values: dict | None) -> None:
        if not values or self.active_profile is None:
            return
        if not all((values["username"], values["provider"], values["model"], values["endpoint"])):
            self._set_status("All profile fields are required.")
            return
        profile = self.active_profile
        previous = (
            profile.username, profile.provider, profile.currentmodel,
            profile.endpoint, profile.memory_enabled,
        )
        profile.username = values["username"]
        profile.provider = values["provider"]
        profile.currentmodel = values["model"]
        profile.endpoint = values["endpoint"]
        profile.memory_enabled = values["memory"]
        try:
            if profile.memory_enabled:
                memory_file = Path(profile.memory_path)
                if not memory_file.is_absolute():
                    memory_file = PROFILE_FILE.parent / memory_file
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                memory_file.touch(exist_ok=True)
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError, ValueError) as exc:
            (
                profile.username, profile.provider, profile.currentmodel,
                profile.endpoint, profile.memory_enabled,
            ) = previous
            self._set_status(f"Could not update profile: {exc}")
            return
        self._render_profiles()
        self._set_status(f"Updated profile | {self._profile_status()}")

    def action_delete_profile(self) -> None:
        if self.active_profile is None:
            self._set_status("No active profile.")
            return
        if len(self.profiles) <= 1:
            self._set_status("The last profile cannot be deleted.")
            return
        self.push_screen(
            ConfirmDeleteProfilePrompt(self.active_profile.profilename),
            self._delete_profile_result,
        )

    def _delete_profile_result(self, confirmed: bool) -> None:
        profile = self.active_profile
        if not confirmed or profile is None:
            return
        remaining = [item for item in self.profiles if item is not profile]
        try:
            save_profiles(PROFILE_FILE, remaining)
        except (StorageError, OSError) as exc:
            self._set_status(f"Could not delete profile: {exc}")
            return
        self.profiles = remaining
        self.active_profile = self.profiles[0]
        self._render_profiles()
        self._render_chats()
        self._set_status(
            f"Deleted profile: {profile.profilename}. Its memory file was retained."
        )

    def action_edit_memory(self) -> None:
        profile = self.active_profile
        if profile is None:
            self._set_status("No active profile.")
            return
        memory_file = Path(profile.memory_path)
        if not memory_file.is_absolute():
            memory_file = PROFILE_FILE.parent / memory_file
        try:
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            memory_file.touch(exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(memory_file))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(memory_file)])
            else:
                subprocess.Popen(["xdg-open", str(memory_file)])
        except (OSError, AttributeError) as exc:
            self._set_status(f"Could not open memory editor: {exc}")
            return
        self._set_status(f"Opened memory file: {memory_file.name} (Ctrl+Shift+M)")

    def action_list_models(self) -> None:
        profile = self.active_profile
        if profile is None:
            self._set_status("No active profile.")
            return
        if self._busy:
            self._set_status("Wait for the current provider request to finish.")
            return
        self._busy = True
        self._set_status(f"Loading models from {profile.provider}...")
        self.run_worker(
            partial(self._fetch_models, profile),
            exclusive=True,
            thread=True,
        )

    def _fetch_models(self, profile: Profile) -> None:
        try:
            models = get_provider(profile.provider).list_models(profile.endpoint)
            self.call_from_thread(self._models_loaded, profile, models)
        except (ProviderError, ValueError, OSError) as exc:
            self.call_from_thread(self._finish_with_error, str(exc))

    def _models_loaded(self, profile: Profile, models: list[str]) -> None:
        self._busy = False
        if not models:
            self._set_status("Provider returned no models or does not support model listing.")
            return
        self.push_screen(
            ModelPickerScreen(models),
            lambda selected: self._apply_selected_model(profile, selected),
        )

    def _apply_selected_model(self, profile: Profile, selected: str | None) -> None:
        if not selected:
            return
        previous = profile.currentmodel
        profile.currentmodel = selected
        try:
            save_profiles(PROFILE_FILE, self.profiles)
        except (StorageError, OSError) as exc:
            profile.currentmodel = previous
            self._set_status(f"Could not save model selection: {exc}")
            return
        self._set_status(f"Selected model: {selected}" if profile is self.active_profile
                         else f"Updated {profile.profilename} model: {selected}")

    def action_focus_profiles(self) -> None:
        self.query_one("#profiles", ListView).focus()
        self._set_status("Choose a profile using UP/DOWN and Enter.")

    def action_refresh_chats(self) -> None:
        self._render_chats()
        self._set_status("Chat list refreshed.")


    def on_unmount(self) -> None:
        self.provider_sessions.close()


def main() -> None:
    ConnectApp().run()


class PopupMenu(ModalScreen[str | None]):
    CSS = """
    PopupMenu { align: left top; }
    #menu-panel { width: 90%; max-width: 34; height: auto; max-height: 80%; margin: 1 0 0 1; border: round $primary; background: $panel; padding: 1; }
    #menu-items { height: auto; max-height: 70%; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]
    def __init__(self, items):
        super().__init__()
        self.items = items
    def compose(self):
        with Vertical(id="menu-panel"):
            yield Label("POWER SOCKET  /  MENU")
            self._item_actions = {}
            menu_items = []
            for index, (action, label) in enumerate(self.items):
                item_id = f"menu-item-{index}"
                self._item_actions[item_id] = action
                menu_items.append(ListItem(Label(label), id=item_id))
            yield ListView(*menu_items, id="menu-items")

    def on_list_view_selected(self, event):
        if event.list_view.id == "menu-items":
            self.dismiss(self._item_actions.get(event.item.id))
    def action_cancel(self):
        self.dismiss("back")


class GeneralSettingsMenu(PopupMenu):
    def __init__(self):
        super().__init__([("export", "Dataset export"), ("context", "Shared resource paths"), ("back", "Back")])


class ExportSettingsPrompt(ModalScreen[dict | None]):
    CSS = """
    ExportSettingsPrompt { align: center middle; }
    #dialog { width: 90%; max-width: 68; height: auto; border: round $primary; background: $panel; padding: 1 2; }
    #dialog-buttons { height: 3; margin-top: 1;  }
    #dialog-buttons Button { width: 1fr; }
    #cancel { margin-right: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]
    def __init__(self, settings):
        super().__init__()
        self.settings = dict(settings)
    def compose(self):
        with Vertical(id="dialog"):
            yield Label("GENERAL SETTINGS ? DATASET EXPORT")
            yield Checkbox("Allow local dataset export", value=self.settings["dataset_export_enabled"], id="export-enabled")
            yield Label(f"Selected chat files: {len(self.settings['selected_chats'])}")
            yield Label(f"Selected chat folders: {len(self.settings['selected_folders'])}")
            yield Label(f"Custom redaction terms: {len(self.settings['redact_terms'])}")
            yield Label("Use python -m power_socket settings to select files/folders and edit redaction terms.")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="cancel")
                yield Button("Save", id="save", variant="primary")
    def on_button_pressed(self, event):
        if event.button.id != "save":
            self.dismiss(None)
            return
        self.settings["dataset_export_enabled"] = self.query_one("#export-enabled", Checkbox).value
        self.dismiss(self.settings)
    def action_cancel(self):
        self.dismiss(None)


class SharedResourcesPrompt(ModalScreen[dict | None]):
    CSS = """
    SharedResourcesPrompt { align: center middle; }
    #dialog { width: 90%; max-width: 78; height: auto; max-height: 92%; border: round $primary; background: $panel; padding: 1 2; overflow-y: auto; }
    #dialog Input { height: 3; }
    #dialog .field-label { height: 1; color: $text-muted; }
    #dialog-buttons { height: 3; margin-top: 1;  }
    #dialog-buttons Button { width: 1fr; }
    #cancel { margin-right: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]
    def __init__(self, focus: str, values: dict):
        super().__init__()
        self.focus = focus
        self.values = dict(values)
    def compose(self):
        with Vertical(id="dialog"):
            yield Label("SHARED RESOURCES ? ALL PROFILES")
            yield Label("Instructions file (.jsonl)", classes="field-label")
            yield Input(value=self.values.get("instructions", ""), placeholder="Absolute path to Instructions JSONL", id="instructions")
            yield Label("Memory file (.md)", classes="field-label")
            yield Input(value=self.values.get("memory", ""), placeholder="Absolute path to shared Memory Markdown", id="memory")
            yield Label("Skills root folder", classes="field-label")
            yield Input(value=self.values.get("skills", ""), placeholder="Absolute path to Skills folder", id="skills")
            yield Label("Paths are references only. Files are not copied or moved.")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="cancel")
                yield Button("Save paths", id="save", variant="primary")
    def on_button_pressed(self, event):
        if event.button.id != "save":
            self.dismiss(None)
            return
        self.dismiss({"instructions": self.query_one("#instructions", Input).value.strip(), "memory": self.query_one("#memory", Input).value.strip(), "skills": self.query_one("#skills", Input).value.strip()})
    def action_cancel(self):
        self.dismiss(None)


class SettingsMenu(PopupMenu):
    def __init__(self):
        super().__init__([("profiles", "Profile"), ("memory", "Memory"), ("general", "General"), ("back", "Back")])


class ProfileMenu(PopupMenu):
    def __init__(self):
        super().__init__([("select", "Select profile"), ("create", "Create profile"), ("edit", "Edit current profile"), ("delete", "Delete current profile"), ("provider", "Provider configuration"), ("back", "Back")])


class ProviderConfigMenu(PopupMenu):
    def __init__(self):
        super().__init__([("provider", "Change provider / endpoint"), ("model", "Change current model"), ("parameters", "Model parameters"), ("back", "Back")])


class ProviderEndpointPrompt(ModalScreen[dict | None]):
    CSS = """
    ProviderEndpointPrompt { align: center middle; }
    #dialog { width: 90%; max-width: 68; height: auto; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { height: 3; }
    #dialog .field-label { height: 1; color: $text-muted; }
    #dialog-buttons { height: 3; }
    #dialog-buttons Button { width: 1fr; }
    #cancel { margin-right: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self, profile: Profile):
        super().__init__()
        self.profile = profile

    def compose(self):
        with Vertical(id="dialog"):
            yield Label(f"PROVIDER CONFIGURATION: {self.profile.profilename}")
            yield Label("Provider ID", classes="field-label")
            yield Input(value=self.profile.provider, placeholder="ollama / openai_compatible", id="provider-id")
            yield Label("Provider endpoint", classes="field-label")
            yield Input(value=self.profile.endpoint, placeholder="http://127.0.0.1:11434", id="provider-endpoint")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="cancel")
                yield Button("Save", variant="primary", id="save")

    def on_button_pressed(self, event):
        if event.button.id != "save":
            self.dismiss(None)
            return
        self.dismiss({
            "profile": self.profile,
            "provider": self.query_one("#provider-id", Input).value.strip(),
            "endpoint": self.query_one("#provider-endpoint", Input).value.strip(),
        })

    def action_cancel(self):
        self.dismiss(None)


class ModelParametersPrompt(ModalScreen[dict | None]):
    CSS = """
    ModelParametersPrompt { align: center middle; }
    #dialog { width: 90%; max-width: 64; height: auto; max-height: 92%; border: round $primary; background: $panel; padding: 1 2; overflow-y: auto; }
    #dialog Input { height: 1; margin-bottom: 0; }
    #dialog .field-label { height: 1; color: $text-muted; }
    #thinking-mode { width: 100%; height: auto; min-height: 3; }
    #dialog-buttons { height: 3; margin-top: 1;  }
    #dialog-buttons Button { width: 1fr; }
    #cancel { margin-right: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Back")]
    FIELDS = (("temperature", "Temperature"), ("top_p", "Top P"), ("top_k", "Top K"), ("context_length", "Context length"), ("max_tokens", "Max tokens"))
    def __init__(self, values=None, provider="ollama"):
        super().__init__()
        self.values = values or {}
        self.provider = provider
    def compose(self):
        with Vertical(id="dialog"):
            yield Label("MODEL PARAMETERS")
            for key, label in self.FIELDS:
                yield Label(label, classes="field-label")
                yield Input(value=str(self.values.get(key, "")), placeholder=f"{label} (optional)", id=key)
            yield Checkbox("Thinking mode (if supported)",
                           value=bool(self.values.get("thinking_mode", False)), id="thinking-mode")
            if self.provider.lower() != "ollama":
                yield Label("Thinking mode is stored but not sent to OpenAI-compatible APIs. Top K and Context length are also not sent.")
            with Horizontal(id="dialog-buttons"):
                yield Button("Back", id="cancel")
                yield Button("Save parameters", id="save", variant="primary")
    def on_button_pressed(self, event):
        if event.button.id != "save":
            self.dismiss(None)
            return
        values = {}
        try:
            for key, _ in self.FIELDS:
                raw = self.query_one(f"#{key}", Input).value.strip()
                if raw:
                    value = float(raw) if key in {"temperature", "top_p"} else int(raw)
                    if value < 0:
                        raise ValueError(f"{key} cannot be negative")
                    values[key] = value
            values["thinking_mode"] = self.query_one("#thinking-mode", Checkbox).value
            self.dismiss(values)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
    def action_cancel(self):
        self.dismiss(None)
