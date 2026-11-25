from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Profile:
    profilename: str
    username: str
    provider: str
    currentmodel: str
    memory_enabled: bool
    memory_path: str
    endpoint: str = "http://127.0.0.1:11434"

    @property
    def memory_file(self) -> Path:
        return Path(self.memory_path)
