"""Provider interface and fallback rules, with fake providers: no network, no API key."""
import json

import pytest
from pydantic import BaseModel

from src import llm_client


class Answer(BaseModel):
    text: str


class FakeProvider:
    def __init__(self, name, outcome):
        self.name, self.outcome, self.model = name, outcome, f"{name}-model"

    def generate(self, prompt, schema, system_instruction=None, temperature=None):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return {"parsed": self.outcome, "finish_reason": "STOP", "provider": self.name, "model": self.model,
                "input_tokens": 1, "output_tokens": 1}


@pytest.fixture
def providers(monkeypatch):
    outcomes = {}
    monkeypatch.setattr(llm_client, "make_provider", lambda name, model=None: FakeProvider(name, outcomes[name]))
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_FALLBACK_PROVIDER", raising=False)
    return outcomes


def test_primary_success_is_not_a_fallback(providers):
    providers["gemini"] = Answer(text="ok")
    result = llm_client.generate("p", Answer)
    assert (result["provider"], result["fallback_used"], result["fallback_reason"]) == ("gemini", False, None)


def test_without_a_configured_fallback_the_error_propagates(providers):
    providers["gemini"] = RuntimeError("quota exceeded")
    with pytest.raises(RuntimeError, match="quota exceeded"):
        llm_client.generate("p", Answer)


def test_failure_switches_to_the_fallback_and_says_so(providers, monkeypatch, caplog):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    providers.update(gemini=RuntimeError("503 overloaded"), ollama=Answer(text="local"))
    result = llm_client.generate("p", Answer)
    assert (result["provider"], result["model"], result["fallback_used"]) == ("ollama", "ollama-model", True)
    assert "gemini failed: RuntimeError: 503 overloaded" in result["fallback_reason"]
    assert "using fallback ollama" in caplog.text


def test_invalid_output_also_triggers_the_fallback(providers, monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    providers.update(gemini=None, ollama=Answer(text="local"))  # e.g. truncated JSON: nothing parsed

    def validate(result):
        if result["parsed"] is None:
            raise RuntimeError("incomplete draft")

    result = llm_client.generate("p", Answer, validate=validate)
    assert result["fallback_used"] and "incomplete draft" in result["fallback_reason"]


def test_both_failing_reports_both(providers, monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    providers.update(gemini=RuntimeError("primary down"), ollama=RuntimeError("no local model"))
    with pytest.raises(RuntimeError, match="primary down.*no local model"):
        llm_client.generate("p", Answer)


def test_ollama_provider_sends_schema_and_system_instruction(monkeypatch):
    sent = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"message": {"content": '{"text": "hi"}'}, "done_reason": "stop",
                               "prompt_eval_count": 7, "eval_count": 3}).encode()

    def fake_urlopen(request, timeout):
        sent.update(url=request.full_url, body=json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OLLAMA_MODEL", "llama-local")
    result = llm_client.OllamaProvider().generate("user text", Answer, system_instruction="rules", temperature=0.2)
    assert result["parsed"] == Answer(text="hi") and result["provider"] == "ollama" and result["input_tokens"] == 7
    assert sent["url"].endswith("/api/chat") and sent["body"]["format"]["properties"]["text"]["type"] == "string"
    assert sent["body"]["messages"][0] == {"role": "system", "content": "rules"}


def test_unknown_provider_is_a_clear_error():
    with pytest.raises(RuntimeError, match="Unknown LLM provider"):
        llm_client.make_provider("mystery")
