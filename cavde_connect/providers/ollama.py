import json
import urllib.error
import urllib.request

from .base import Generation, Provider, ProviderError


class OllamaProvider(Provider):
    """Minimal Ollama /api/chat adapter using the Python standard library."""

    def list_models(self, endpoint: str) -> list[str]:
        url = endpoint.rstrip("/") + "/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("models", [])
            return sorted(
                item["name"] for item in models
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Ollama model listing failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Cannot connect to Ollama at {url}: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            raise ProviderError(f"Invalid model list from Ollama: {exc}") from exc

    def generate(self, model: str, messages: list[dict[str, str]], endpoint: str) -> Generation:
        url = endpoint.rstrip("/") + "/api/chat"
        body = json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload.get("message", {}).get("content")
            if not isinstance(text, str):
                raise ProviderError("Ollama returned an unexpected response.")
            return Generation(text=text)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ProviderError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Cannot connect to Ollama at {url}: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(f"Invalid response from Ollama: {exc}") from exc
