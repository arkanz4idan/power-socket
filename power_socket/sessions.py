from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .providers.registry import get_provider


@dataclass
class _SessionEntry:
    provider: object
    transport: requests.Session | None
    lock: RLock = field(default_factory=RLock)


class ProviderSessionManager:
    """Reuse provider adapters and HTTP keep-alive sessions per configuration."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _SessionEntry] = {}
        self._lock = RLock()

    @staticmethod
    def _key(provider_name: str, endpoint: str) -> tuple[str, str]:
        return provider_name.strip().lower(), endpoint.rstrip("/")

    def _entry(self, provider_name: str, endpoint: str) -> _SessionEntry:
        key = self._key(provider_name, endpoint)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                return entry
            transport = None
            normalized = key[0].replace("-", "_")
            if normalized in {"ollama", "llama.cpp", "llamacpp", "openai", "openai_compatible"}:
                transport = requests.Session()
                transport.headers.update({"User-Agent": "PowerSocket/0.2"})
                retry = Retry(
                    total=2, connect=2, read=0, status=0,
                    allowed_methods=frozenset({"GET", "POST"}),
                    backoff_factor=0.2,
                )
                adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
                transport.mount("http://", adapter)
                transport.mount("https://", adapter)
                provider = get_provider(provider_name, http_session=transport)
            else:
                # Third-party adapters retain the original Provider contract.
                provider = get_provider(provider_name)
            entry = _SessionEntry(provider=provider, transport=transport)
            self._entries[key] = entry
            return entry

    def is_ready(self, provider_name: str, endpoint: str) -> bool:
        with self._lock:
            return self._key(provider_name, endpoint) in self._entries

    def generate(self, provider_name: str, model: str,
                 messages: list[dict[str, str]], endpoint: str,
                 options: dict | None = None):
        entry = self._entry(provider_name, endpoint)
        with entry.lock:
            if options and hasattr(entry.provider, "generate_with_options"):
                return entry.provider.generate_with_options(model, messages, endpoint, options)
            return entry.provider.generate(model, messages, endpoint)

    def list_models(self, provider_name: str, endpoint: str) -> list[str]:
        entry = self._entry(provider_name, endpoint)
        with entry.lock:
            return entry.provider.list_models(endpoint)

    def invalidate(self, provider_name: str, endpoint: str) -> None:
        key = self._key(provider_name, endpoint)
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry and entry.transport:
            entry.transport.close()

    def close(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            if entry.transport:
                entry.transport.close()
