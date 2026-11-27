from importlib.metadata import entry_points

from .base import Provider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


def get_provider(name: str, http_session=None) -> Provider:
    key = name.strip().lower().replace("-", "_")
    if key == "ollama":
        return OllamaProvider(http_session=http_session)
    if key in {"llama.cpp", "llamacpp", "openai_compatible", "openai"}:
        return OpenAICompatibleProvider(http_session=http_session)

    # Third-party packages keep the original zero-argument adapter contract.
    for candidate in entry_points(group="power_socket.providers"):
        candidate_key = candidate.name.strip().lower().replace("-", "_")
        if candidate_key == key:
            provider_type = candidate.load()
            provider = provider_type()
            if not isinstance(provider, Provider):
                raise TypeError(
                    f"External provider {candidate.name!r} must implement Provider"
                )
            return provider
    raise ValueError(f"Unknown provider adapter: {name!r}")
