from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Profile:
    profilename: str
    username: str
    provider: str
    currentmodel: str
    memory_enabled: bool
    memory_path: str
    endpoint: str = "http://127.0.0.1:11434"
    model_parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def memory_file(self) -> Path:
        return Path(self.memory_path)
