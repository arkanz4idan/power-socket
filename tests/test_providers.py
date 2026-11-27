import unittest
from unittest.mock import Mock, patch

from power_socket.providers import registry
from power_socket.providers.base import Generation, Provider
from power_socket.providers.ollama import OllamaProvider
from power_socket.providers.openai_compatible import OpenAICompatibleProvider
from power_socket.sessions import ProviderSessionManager


class ExternalStubProvider(Provider):
    def generate(self, model, messages, endpoint):
        return Generation("external adapter response")


class FakeEntryPoint:
    name = "external-demo"

    def load(self):
        return ExternalStubProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.text = "server error"

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class ProviderTests(unittest.TestCase):
    def test_ollama_payload_and_response(self):
        http = Mock()
        http.post.return_value = FakeResponse({"message": {"content": "Hello from Ollama"}})
        result = OllamaProvider(http).generate(
            "small", [{"role": "user", "content": "Hello"}],
            "http://127.0.0.1:11434/"
        )
        self.assertEqual(result.text, "Hello from Ollama")
        args, kwargs = http.post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(kwargs["json"]["model"], "small")
        self.assertFalse(kwargs["json"]["stream"])

    def test_ollama_generation_options_map_to_native_options(self):
        http = Mock()
        http.post.return_value = FakeResponse({"message": {"content": "ok"}})
        OllamaProvider(http).generate_with_options(
            "small", [], "http://localhost:11434",
            {"temperature": 0.4, "top_p": 0.8, "top_k": 30,
             "context_length": 4096, "max_tokens": 256},
        )
        options = http.post.call_args.kwargs["json"]["options"]
        self.assertEqual(options, {
            "temperature": 0.4, "top_p": 0.8, "top_k": 30,
            "num_ctx": 4096, "num_predict": 256,
        })

    def test_ollama_thinking_mode_is_forwarded(self):
        http = Mock()
        http.post.return_value = FakeResponse({"message": {"content": "thinking response"}})
        OllamaProvider(http).generate_with_options(
            "reasoning-model", [], "http://localhost:11434", {"thinking_mode": True}
        )
        self.assertIs(http.post.call_args.kwargs["json"]["think"], True)

    def test_openai_compatible_omits_nonstandard_model_options(self):
        http = Mock()
        http.post.return_value = FakeResponse({
            "choices": [{"message": {"content": "ok"}}]
        })
        OpenAICompatibleProvider(http).generate_with_options(
            "local", [], "http://localhost:8080/v1",
            {"temperature": 0.5, "top_p": 0.9, "top_k": 40,
             "context_length": 4096, "max_tokens": 100},
        )
        payload = http.post.call_args.kwargs["json"]
        self.assertEqual(payload["temperature"], 0.5)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["max_tokens"], 100)
        self.assertNotIn("top_k", payload)
        self.assertNotIn("context_length", payload)

    def test_ollama_model_discovery(self):
        http = Mock()
        http.get.return_value = FakeResponse({
            "models": [{"name": "z-model"}, {"name": "a-model"}]
        })
        models = OllamaProvider(http).list_models("http://127.0.0.1:11434")
        self.assertEqual(models, ["a-model", "z-model"])
        self.assertEqual(http.get.call_args.args[0], "http://127.0.0.1:11434/api/tags")

    def test_openai_compatible_payload_and_response(self):
        http = Mock()
        http.post.return_value = FakeResponse({
            "choices": [{"message": {"content": "Hello from compatible API"}}]
        })
        result = OpenAICompatibleProvider(http).generate(
            "local-model", [{"role": "user", "content": "Hello"}],
            "http://127.0.0.1:8080/v1"
        )
        self.assertEqual(result.text, "Hello from compatible API")
        self.assertEqual(
            http.post.call_args.args[0],
            "http://127.0.0.1:8080/v1/chat/completions",
        )

    def test_openai_compatible_model_discovery(self):
        http = Mock()
        http.get.return_value = FakeResponse({
            "data": [{"id": "local-z"}, {"id": "local-a"}]
        })
        models = OpenAICompatibleProvider(http).list_models("http://127.0.0.1:8080/v1")
        self.assertEqual(models, ["local-a", "local-z"])
        self.assertEqual(http.get.call_args.args[0], "http://127.0.0.1:8080/v1/models")

    def test_external_provider_entry_point(self):
        with patch.object(registry, "entry_points", return_value=[FakeEntryPoint()]):
            provider = registry.get_provider("external-demo")
        self.assertIsInstance(provider, ExternalStubProvider)
        self.assertEqual(
            provider.generate("demo", [{"role": "user", "content": "hi"}], "").text,
            "external adapter response",
        )

    def test_session_manager_reuses_adapter_and_transport_for_repeated_prompts(self):
        manager = ProviderSessionManager()
        with patch("power_socket.sessions.requests.Session") as session_factory:
            transport = session_factory.return_value
            transport.post.return_value = FakeResponse({"message": {"content": "ok"}})
            first = manager.generate("ollama", "model", [], "http://localhost:11434")
            second = manager.generate("ollama", "model", [], "http://localhost:11434")
            self.assertEqual(first.text, "ok")
            self.assertEqual(second.text, "ok")
            session_factory.assert_called_once_with()
            self.assertEqual(transport.post.call_count, 2)
            self.assertTrue(manager.is_ready("ollama", "http://localhost:11434/"))
            manager.close()
            transport.close.assert_called_once()

    def test_session_manager_separates_endpoints_and_invalidates_one(self):
        manager = ProviderSessionManager()
        with patch("power_socket.sessions.requests.Session") as session_factory:
            session_factory.return_value.post.return_value = FakeResponse(
                {"message": {"content": "ok"}}
            )
            manager.generate("ollama", "model", [], "http://localhost:11434")
            manager.generate("ollama", "model", [], "http://localhost:11435")
            self.assertEqual(session_factory.call_count, 2)
            manager.invalidate("ollama", "http://localhost:11434/")
            self.assertFalse(manager.is_ready("ollama", "http://localhost:11434"))
            self.assertTrue(manager.is_ready("ollama", "http://localhost:11435"))
            manager.close()


if __name__ == "__main__":
    unittest.main()
