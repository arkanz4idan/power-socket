from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """A provider connection or generation failure."""


@dataclass(slots=True)
class Generation:
    text: str


class Provider(ABC):
    """Python-side adapter contract. Adapters may bridge to any language."""

    @abstractmethod
    def generate(self, model: str, messages: list[dict[str, str]], endpoint: str) -> Generation:
        """Generate one response from normalized role/content messages."""
        raise NotImplementedError

    def generate_with_options(self, model: str, messages: list[dict[str, str]],
                              endpoint: str, options: dict) -> Generation:
        """Optional generation settings; legacy adapters safely ignore unsupported options."""
        return self.generate(model, messages, endpoint)

    def list_models(self, endpoint: str) -> list[str]:
        """Return available model identifiers when the provider supports discovery."""
        return []
