"""Advisory semantic checker, with fake backends: no model download, no network, no API key."""
from types import SimpleNamespace

import pytest

from src import semantic_checker
from src.safety_evaluator import evaluate_revision
from src.semantic_checker import LlmJudgeBackend, NliBackend, apply_semantic_check, check

SOURCE = """Pump Maintenance
SAFETY WARNINGS
WARNING: Never open the pump casing while the motor is running.
PROCEDURE
1. Switch off the pump motor at the local isolator.
2. Close the inlet valve and the outlet valve.
"""
WARNING = "WARNING: Never open the pump casing while the motor is running."
CLEAN = f"DRAFT:\nPump Maintenance\n{WARNING}\n1. Switch off the pump motor at the local isolator.\n2. Close the inlet valve and the outlet valve.\n"
# Contradicts the warning in different words, which the word rules cannot see.
SNEAKY = CLEAN + "3. Remove the housing cover with the drive still turning to save time.\n"


class FakeBackend:
    name = "fake"

    def __init__(self, pairs=(), error=None):
        self.pairs, self.error, self.calls = list(pairs), error, []

    def find_contradictions(self, original_items, draft_items):
        self.calls.append((original_items, draft_items))
        if self.error:
            raise self.error
        return [(o, d, 0.93, "reason") for o, d in self.pairs if o in original_items and d in draft_items]


SNEAKY_PAIR = (WARNING, "Remove the housing cover with the drive still turning to save time.")


def test_off_by_default_changes_nothing(monkeypatch):
    monkeypatch.delenv("SEMANTIC_CHECK", raising=False)
    evaluation = evaluate_revision(SOURCE, SNEAKY)
    assert apply_semantic_check(evaluation, SOURCE, SNEAKY) is evaluation


def test_check_returns_labelled_advisory_findings():
    [finding] = check([WARNING], [SNEAKY_PAIR[1]], FakeBackend([SNEAKY_PAIR]))
    assert finding["advisory"] is True and finding["severity"] == "review"
    assert (finding["type"], finding["backend"], finding["confidence"]) == ("semantic_contradiction", "fake", 0.93)


def test_advisory_finding_raises_pass_to_needs_review():
    evaluation = evaluate_revision(SOURCE, SNEAKY)
    evaluation = {**evaluation, "status": "pass_automated", "findings": []}  # as if the rules saw nothing
    backend = FakeBackend([SNEAKY_PAIR])
    result = apply_semantic_check(evaluation, SOURCE, SNEAKY, backend)
    assert result["status"] == "needs_review"
    assert [f["type"] for f in result["findings"]] == ["semantic_contradiction"]
    assert result["metrics"]["semantic_check"] == {"backend": "fake", "status": "ran", "advisory_findings": 1}
    # The backend sees source warnings and draft steps only, never the model's own summary.
    assert backend.calls[0][0] == [WARNING] and len(backend.calls[0][1]) == 3


def test_semantic_check_never_lowers_a_fail():
    evaluation = evaluate_revision(SOURCE, SNEAKY)
    assert evaluation["status"] == "fail"  # the new step is unsupported by the source
    for backend in (FakeBackend(), FakeBackend([SNEAKY_PAIR])):
        result = apply_semantic_check(evaluation, SOURCE, SNEAKY, backend)
        assert result["status"] == "fail"
        assert result["findings"][:len(evaluation["findings"])] == evaluation["findings"]


def test_backend_error_keeps_the_rule_result():
    evaluation = evaluate_revision(SOURCE, CLEAN)
    result = apply_semantic_check(evaluation, SOURCE, CLEAN, FakeBackend(error=RuntimeError("model down")))
    assert (result["status"], result["findings"]) == (evaluation["status"], evaluation["findings"])
    assert result["metrics"]["semantic_check"]["status"] == "error"
    assert "model down" in result["metrics"]["semantic_check"]["message"]


def test_bad_env_value_is_recorded_not_raised(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CHECK", "maybe")
    evaluation = evaluate_revision(SOURCE, CLEAN)
    result = apply_semantic_check(evaluation, SOURCE, CLEAN)
    assert result["status"] == evaluation["status"] and result["metrics"]["semantic_check"]["status"] == "error"


def test_pairs_already_found_by_the_rules_are_not_repeated():
    draft = CLEAN + "3. Open the pump casing while the motor is running to check the impeller.\n"
    evaluation = evaluate_revision(SOURCE, draft)
    pair = (WARNING, "Open the pump casing while the motor is running to check the impeller.")
    assert any(f["type"] == "contradicts_warning" for f in evaluation["findings"])
    result = apply_semantic_check(evaluation, SOURCE, draft, FakeBackend([pair]))
    assert not any(f["type"] == "semantic_contradiction" for f in result["findings"])


def test_nli_backend_reads_the_contradiction_label(monkeypatch):
    class FakeCrossEncoder:
        config = SimpleNamespace(id2label={0: "entailment", 1: "CONTRADICTION", 2: "neutral"})

        def predict(self, pairs, apply_softmax):
            return [[0.05, 0.9, 0.05] if "housing" in step else [0.7, 0.1, 0.2] for _, step in pairs]

    monkeypatch.setattr(semantic_checker, "load_cross_encoder", lambda name: FakeCrossEncoder())
    found = NliBackend("fake-nli").find_contradictions([WARNING], ["Close the valve.", SNEAKY_PAIR[1]])
    assert [(o, d) for o, d, _, _ in found] == [SNEAKY_PAIR]


def test_llm_backend_maps_indices_and_handles_refusal():
    def client_returning(stop_reason, contradictions):
        parsed = None if contradictions is None else semantic_checker.Judgement(contradictions=contradictions)
        response = SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed)
        messages = SimpleNamespace(parse=lambda **kwargs: client.calls.append(kwargs) or response)
        client = SimpleNamespace(messages=messages, calls=[])
        return client

    steps = ["Close the valve.", SNEAKY_PAIR[1]]
    client = client_returning("end_turn", [
        semantic_checker.Contradiction(warning_index=0, step_index=1, confidence=1.4, reason="cover off while turning"),
        semantic_checker.Contradiction(warning_index=3, step_index=0, confidence=0.9, reason="bad index"),
    ])
    found = LlmJudgeBackend("judge-model", client=client).find_contradictions([WARNING], steps)
    assert found == [(WARNING, SNEAKY_PAIR[1], 1.0, "cover off while turning")]  # clamped, bad index dropped
    assert client.calls[0]["model"] == "judge-model" and client.calls[0]["output_format"] is semantic_checker.Judgement

    with pytest.raises(RuntimeError, match="refusal"):
        LlmJudgeBackend("judge-model", client=client_returning("refusal", None)).find_contradictions([WARNING], steps)
