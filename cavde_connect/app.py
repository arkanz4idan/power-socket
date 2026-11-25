from functools import partial
import os
from pathlib import Path
import re
import subprocess
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from rich.text import Text
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, ListItem, ListView, RichLog,
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
    #dialog { width: 60; height: 11; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { margin-top: 1; }
    #dialog Button { margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New conversation name")
            yield Input(placeholder="e.g. coding-session", id="new-name")
            yield Button("Create", variant="primary", id="create")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#new-name", Input).value if event.button.id == "create" else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

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
    #dialog { width: 76; height: 22; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { height: 1; margin-bottom: 1; }
    #dialog Button { height: 1; margin-top: 0; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Create profile")
            yield Input(placeholder="Profile name", id="profile-name")
            yield Input(placeholder="Username shown in chat", id="profile-user")
            yield Input(value="ollama", placeholder="Provider: ollama / llamacpp / openai_compatible", id="profile-provider")
            yield Input(value="llama3.2", placeholder="Model name", id="profile-model")
            yield Input(value="http://127.0.0.1:11434", placeholder="Provider endpoint", id="profile-endpoint")
            yield Checkbox("Enable this profile's Markdown memory", value=False, id="profile-memory")
            yield Button("Create profile", variant="primary", id="create")
            yield Button("Cancel", id="cancel")

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
    #dialog { width: 76; height: 22; border: round $primary; background: $panel; padding: 1 2; }
    #dialog Input { height: 1; margin-bottom: 1; }
    #dialog Button { height: 1; margin-top: 0; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        p = self.profile
        with Vertical(id="dialog"):
            yield Label(f"Edit profile: {p.profilename}")
            yield Input(value=p.username, placeholder="Username", id="profile-user")
            yield Input(value=p.provider, placeholder="Provider", id="profile-provider")
            yield Input(value=p.currentmodel, placeholder="Model name", id="profile-model")
            yield Input(value=p.endpoint, placeholder="Provider endpoint", id="profile-endpoint")
            yield Checkbox("Enable this profile's Markdown memory", value=p.memory_enabled, id="profile-memory")
            yield Button("Save changes", variant="primary", id="save")
            yield Button("Cancel", id="cancel")

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
            yield Label("Available models — ↑/↓ then Enter")
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


class ConnectApp(App):
    TITLE = "Power Socket"
    SUB_TITLE = "Universal AI terminal client"
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; }
    #sidebar { width: 30; border: round $primary; padding: 1; }
    #workspace { width: 1fr; border: round $secondary; padding: 1; }
    #chat-log { height: 1fr; border: round $surface; padding: 1; overflow-y: auto; }
    #composer { height: 3; }
    #status { height: 1; color: $text-muted; }
    ListView { height: 1fr; }
    """
    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New chat"),
        Binding("ctrl+m", "rename_chat", "Rename chat"),
        Binding("ctrl+d", "delete_chat", "Delete chat"),
        Binding("ctrl+shift+p", "new_profile", "New profile"),
        Binding("ctrl+shift+x", "delete_profile", "Delete profile"),
        Binding("ctrl+e", "edit_profile", "Edit profile"),
        Binding("ctrl+shift+m", "edit_memory", "Edit memory"),
        Binding("ctrl+l", "list_models", "List models"),
        Binding("ctrl+p", "focus_profiles", "Profiles"),
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Label("PROFILES  [Ctrl+P]")
                yield ListView(id="profiles")
                yield Label("CHATS")
                yield ListView(id="chats")
            with Vertical(id="workspace"):
                yield RichLog(
                    id="chat-log", wrap=True, markup=False, auto_scroll=True
                )
                yield Input(placeholder="Message your AI...", id="composer")
                yield Label("Starting...", id="status")
        yield Footer()

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
            self._render_profiles()
            self._render_chats()
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
        view = self.query_one("#profiles", ListView)
        view.clear()
        self._profile_names = [p.profilename for p in self.profiles]
        for profile in self.profiles:
            prefix = "> " if profile is self.active_profile else "  "
            view.append(ListItem(Label(prefix + profile.profilename)))

    def _render_chats(self) -> None:
        view = self.query_one("#chats", ListView)
        view.clear()
        self._chat_names = list_chats(CHAT_DIR)
        for name in self._chat_names:
            prefix = "> " if name == self.active_chat else "  "
            view.append(ListItem(Label(prefix + name)))
        if self.active_chat and self.active_chat in self._chat_names:
            self._load_active_chat()
        elif self._chat_names and not self.active_chat:
            self.active_chat = self._chat_names[0]
            self._load_active_chat()

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
            log.write("Conversation is empty.")
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
        self._set_status("Connecting to provider…")
        self.run_worker(
            partial(self._generate_and_store, profile, self.active_chat, prompt, messages),
            exclusive=True,
            thread=True,
        )

    def _generate_and_store(self, profile: Profile, chat_name: str,
                            prompt: str, messages: list[dict[str, str]]) -> None:
        try:
            response = get_provider(profile.provider).generate(
                profile.currentmodel, messages, profile.endpoint
            )
            append_chat_turn(chat_path(CHAT_DIR, chat_name), prompt, response.text)
            self.call_from_thread(self._after_response, chat_name, prompt, response.text)
        except (ProviderError, ValueError, StorageError, OSError) as exc:
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
            self.query_one("#composer", Input).focus()
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
        self._set_status(f"Loading models from {profile.provider}…")
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
        self._set_status("Choose a profile using ↑/↓ and Enter.")

    def action_refresh_chats(self) -> None:
        self._render_chats()
        self._set_status("Chat list refreshed.")


def main() -> None:
    ConnectApp().run()
