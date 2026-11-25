import io
import json
import unittest
from unittest.mock import patch

from cavde_connect.providers import registry
from cavde_connect.providers.base import Generation, Provider
from cavde_connect.providers.ollama import OllamaProvider
from cavde_connect.providers.openai_compatible import OpenAICompatibleProvider


class ExternalStubProvider(Provider):
    def generate(self, model, messages, endpoint):
        return Generation("external adapter response")


class FakeEntryPoint:
    name = "external-demo"

    def load(self):
        return ExternalStubProvider


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ProviderTests(unittest.TestCase):
    def test_ollama_payload_and_response(self):
        response = FakeResponse(json.dumps({
            "message": {"content": "Hello from Ollama"}
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as open_url:
            result = OllamaProvider().generate(
                "small", [{"role": "user", "content": "Hello"}],
                "http://127.0.0.1:11434/"
            )
        self.assertEqual(result.text, "Hello from Ollama")
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/chat"))
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["model"], "small")
        self.assertFalse(payload["stream"])

    def test_ollama_model_discovery(self):
        response = FakeResponse(json.dumps({
            "models": [{"name": "z-model"}, {"name": "a-model"}]
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as open_url:
            models = OllamaProvider().list_models("http://127.0.0.1:11434")
        self.assertEqual(models, ["a-model", "z-model"])
        self.assertEqual(open_url.call_args.args[0], "http://127.0.0.1:11434/api/tags")

    def test_openai_compatible_payload_and_response(self):
        response = FakeResponse(json.dumps({
            "choices": [{"message": {"content": "Hello from compatible API"}}]
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as open_url:
            result = OpenAICompatibleProvider().generate(
                "local-model", [{"role": "user", "content": "Hello"}],
                "http://127.0.0.1:8080/v1"
            )
        self.assertEqual(result.text, "Hello from compatible API")
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v1/chat/completions"))

    def test_openai_compatible_model_discovery(self):
        response = FakeResponse(json.dumps({
            "data": [{"id": "local-z"}, {"id": "local-a"}]
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as open_url:
            models = OpenAICompatibleProvider().list_models("http://127.0.0.1:8080/v1")
        self.assertEqual(models, ["local-a", "local-z"])
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v1/models"))

    def test_external_provider_entry_point(self):
        with patch.object(registry, "entry_points", return_value=[FakeEntryPoint()]):
            provider = registry.get_provider("external-demo")
        self.assertIsInstance(provider, ExternalStubProvider)
        self.assertEqual(
            provider.generate("demo", [{"role": "user", "content": "hi"}], "").text,
            "external adapter response",
        )


if __name__ == "__main__":
    unittest.main()
