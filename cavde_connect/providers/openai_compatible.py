import json
import os
import urllib.error
import urllib.request

from .base import Generation, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    """Adapter for OpenAI-compatible chat completion APIs (including llama.cpp server)."""

    def list_models(self, endpoint: str) -> list[str]:
        base_url = endpoint.rstrip("/")
        url = base_url + "/models" if base_url.endswith("/v1") else base_url + "/v1/models"
        headers = {}
        api_key = (
            os.environ.get("POWER_SOCKET_API_KEY")
            or os.environ.get("CAVDE_CONNECT_API_KEY")
        )
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("data", [])
            return sorted(
                item["id"] for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Model listing failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Cannot connect to compatible endpoint {url}: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            raise ProviderError(f"Invalid model list: {exc}") from exc

    def generate(self, model: str, messages: list[dict[str, str]], endpoint: str) -> Generation:
        base_url = endpoint.rstrip("/")
        url = base_url + "/chat/completions" if base_url.endswith("/v1") else base_url + "/v1/chat/completions"
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        api_key = (
            os.environ.get("POWER_SOCKET_API_KEY")
            or os.environ.get("CAVDE_CONNECT_API_KEY")
        )
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderError("Provider returned a non-text response.")
            return Generation(text=content)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Cannot connect to compatible endpoint {url}: {exc.reason}") from exc
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(f"Unexpected compatible API response: {exc}") from exc
