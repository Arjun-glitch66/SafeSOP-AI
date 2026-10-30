"""Regional-language output checked by independent back-translation (model calls faked)."""
import pytest

from src import translator

ENGLISH = """DRAFT:
Pump Maintenance
WARNING: Never open the pump casing while the motor is running.
1. Switch off the pump motor at the local isolator.
2. Drain the casing into the 20 litre waste container.

CHANGE SUMMARY:
- none"""
ENGLISH_BODY = ENGLISH.split("DRAFT:\n")[1].split("\n\nCHANGE SUMMARY")[0]


def fake_calls(monkeypatch, back_translation):
    calls = []

    def fake_generate(prompt, schema, system_instruction=None, temperature=None, validate=None):
        calls.append({"prompt": prompt, "system": system_instruction})
        text = "[hi] translated text" if len(calls) == 1 else back_translation
        result = {"parsed": schema(text=text), "provider": "fake", "model": "fake"}
        if validate:
            validate(result)
        return result

    monkeypatch.setattr(translator.llm_client, "generate", fake_generate)
    return calls


def test_translation_then_independent_back_translation(monkeypatch):
    calls = fake_calls(monkeypatch, ENGLISH_BODY)
    translated, back = translator.translate_with_check(ENGLISH, "hi")
    assert (translated, back) == ("[hi] translated text", ENGLISH_BODY)
    assert "into Hindi" in calls[0]["system"] and ENGLISH_BODY in calls[0]["prompt"]
    # The back-translation call sees only the Hindi text, never the English draft.
    assert "from Hindi into English" in calls[1]["system"] and ENGLISH_BODY not in calls[1]["prompt"]
    assert "CHANGE SUMMARY" not in calls[0]["prompt"]  # only the draft is translated
    assert translator.translation_findings(ENGLISH, back, "hi") == []


def test_a_warning_lost_in_translation_is_a_critical_finding():
    dropped = ENGLISH_BODY.replace("WARNING: Never open the pump casing while the motor is running.\n", "")
    findings = translator.translation_findings(ENGLISH, dropped, "hi")
    [lost] = [f for f in findings if f["type"] == "translation_missing_warning"]
    assert lost["severity"] == "critical" and lost["detail"].startswith("Hindi translation (checked by back-translation)")


def test_a_reversed_instruction_in_translation_is_flagged():
    flipped = ENGLISH_BODY.replace("Switch off", "Switch on")
    types = {f["type"] for f in translator.translation_findings(ENGLISH, flipped, "hi")}
    assert "translation_conflicting_instruction" in types


def test_unknown_language_and_empty_translation_are_errors(monkeypatch):
    with pytest.raises(ValueError):
        translator.translate_with_check(ENGLISH, "xx")
    fake_calls(monkeypatch, "   ")
    with pytest.raises(RuntimeError, match="empty"):
        translator.translate_with_check(ENGLISH, "ta")
