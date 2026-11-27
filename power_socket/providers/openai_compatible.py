import os

import requests

from .base import Generation, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    """OpenAI-compatible chat completion adapter with reusable HTTP transport."""

    def __init__(self, http_session: requests.Session | None = None) -> None:
        self.http = http_session or requests.Session()
        self._owns_session = http_session is None

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {}
        api_key = os.environ.get("POWER_SOCKET_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _models_url(endpoint: str) -> str:
        base = endpoint.rstrip("/")
        return base + "/models" if base.endswith("/v1") else base + "/v1/models"

    @staticmethod
    def _chat_url(endpoint: str) -> str:
        base = endpoint.rstrip("/")
        return base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"

    def list_models(self, endpoint: str) -> list[str]:
        url = self._models_url(endpoint)
        try:
            response = self.http.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            data = response.json().get("data", [])
            return sorted(item["id"] for item in data
                          if isinstance(item, dict) and isinstance(item.get("id"), str))
        except requests.HTTPError as exc:
            raise ProviderError(f"Model listing failed: {exc}") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Cannot connect to compatible endpoint {url}: {exc}") from exc
        except (ValueError, AttributeError) as exc:
            raise ProviderError(f"Invalid model list: {exc}") from exc

    def generate(self, model: str, messages: list[dict[str, str]], endpoint: str) -> Generation:
        return self.generate_with_options(model, messages, endpoint, {})

    def generate_with_options(self, model: str, messages: list[dict[str, str]],
                              endpoint: str, options: dict) -> Generation:
        url = self._chat_url(endpoint)
        payload = {"model": model, "messages": messages, "stream": False}
        # These are standard OpenAI-compatible fields. Non-standard Top K and
        # context length are deliberately not sent to avoid unsupported options.
        for key in ("temperature", "top_p", "max_tokens"):
            if key in options and options[key] is not None:
                payload[key] = options[key]
        try:
            response = self.http.post(url, json=payload, headers=self._headers(), timeout=90)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderError("Provider returned a non-text response.")
            return Generation(text=content)
        except requests.HTTPError as exc:
            detail = exc.response.text[:2048] if exc.response is not None else str(exc)
            raise ProviderError(f"Compatible API request failed: {detail}") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Cannot connect to compatible endpoint {url}: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"Unexpected compatible API response: {exc}") from exc

    def close(self) -> None:
        if self._owns_session:
            self.http.close()
