"""Generator tests with the Gemini client faked: no network, no API key."""
from types import SimpleNamespace

import pytest

from src import sop_generator
from src.safety_evaluator import extract_draft_section


class FakeClient:
    last_call = {}

    def __init__(self, api_key, http_options):
        FakeClient.last_call["http_options"] = http_options
        self.models = self

    def generate_content(self, model, contents, config):
        FakeClient.last_call.update(model=model, config=config)
        return FakeClient.response


def fake_response(parsed=None, text=""):
    usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
    return SimpleNamespace(parsed=parsed, text=text, usage_metadata=usage)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.delenv("GEMINI_TEMPERATURE", raising=False)
    monkeypatch.setattr(sop_generator.genai, "Client", FakeClient)


def test_structured_output_is_rendered_as_sections():
    FakeClient.response = fake_response(parsed=sop_generator.SopDraft(
        draft="1. Isolate power.", change_summary="none", preserved_safety_requirements="all",
        unresolved_questions="none", source_limitations="none"))
    result = sop_generator.generate_sop("source", "change")

    assert result["structured_output"] is True
    assert result["prompt_version"] == "v2" and result["temperature"] == 0.2
    assert extract_draft_section(result["text"]) == ("1. Isolate power.", True)
    config = FakeClient.last_call["config"]
    assert config.response_mime_type == "application/json" and config.response_schema is sop_generator.SopDraft
    assert 429 in FakeClient.last_call["http_options"].retry_options.http_status_codes


def test_truncated_json_is_rejected_not_saved():
    response = fake_response(parsed=None, text='{"draft": "1. Switch off')
    response.candidates = [SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))]
    FakeClient.response = response
    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        sop_generator.generate_sop("source", "change")


def test_empty_draft_and_bad_temperature_raise(monkeypatch):
    FakeClient.response = fake_response(parsed=sop_generator.SopDraft(
        draft="  ", change_summary="", preserved_safety_requirements="",
        unresolved_questions="", source_limitations=""))
    with pytest.raises(RuntimeError, match="complete structured draft"):
        sop_generator.generate_sop("source", "change")

    monkeypatch.setenv("GEMINI_TEMPERATURE", "hot")
    with pytest.raises(RuntimeError, match="GEMINI_TEMPERATURE"):
        sop_generator.generate_sop("source", "change")


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        sop_generator.generate_sop("source", "change")
