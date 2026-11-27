import requests

from .base import Generation, Provider, ProviderError


class OllamaProvider(Provider):
    """Ollama /api/chat adapter with a reusable HTTP session."""

    def __init__(self, http_session: requests.Session | None = None) -> None:
        self.http = http_session or requests.Session()
        self._owns_session = http_session is None

    def list_models(self, endpoint: str) -> list[str]:
        url = endpoint.rstrip("/") + "/api/tags"
        try:
            response = self.http.get(url, timeout=10)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models", [])
            return sorted(item["name"] for item in models
                          if isinstance(item, dict) and isinstance(item.get("name"), str))
        except requests.HTTPError as exc:
            raise ProviderError(f"Ollama model listing failed: {exc}") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Cannot connect to Ollama at {url}: {exc}") from exc
        except (ValueError, AttributeError) as exc:
            raise ProviderError(f"Invalid model list from Ollama: {exc}") from exc

    def generate(self, model: str, messages: list[dict[str, str]], endpoint: str) -> Generation:
        return self.generate_with_options(model, messages, endpoint, {})

    def generate_with_options(self, model: str, messages: list[dict[str, str]],
                              endpoint: str, options: dict) -> Generation:
        url = endpoint.rstrip("/") + "/api/chat"
        ollama_options = {}
        mapping = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k",
                   "context_length": "num_ctx", "max_tokens": "num_predict"}
        for source, target in mapping.items():
            if source in options and options[source] is not None:
                ollama_options[target] = options[source]
        body = {"model": model, "messages": messages, "stream": False}
        if ollama_options:
            body["options"] = ollama_options
        if "thinking_mode" in options:
            body["think"] = bool(options["thinking_mode"])
        try:
            response = self.http.post(url, json=body, timeout=90)
            response.raise_for_status()
            payload = response.json()
            text = payload.get("message", {}).get("content")
            if not isinstance(text, str):
                raise ProviderError("Ollama returned an unexpected response.")
            return Generation(text=text)
        except requests.HTTPError as exc:
            detail = exc.response.text[:2048] if exc.response is not None else str(exc)
            raise ProviderError(f"Ollama request failed: {detail}") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Cannot connect to Ollama at {url}: {exc}") from exc
        except (ValueError, AttributeError) as exc:
            raise ProviderError(f"Invalid response from Ollama: {exc}") from exc

    def close(self) -> None:
        if self._owns_session:
            self.http.close()
