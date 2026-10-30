"""evaluate_structured_revision(): prompt-v3 drafts matched by source id, not by text similarity."""
from src.safety_evaluator import EVALUATOR_VERSION, evaluate_structured_revision, number_source_items
from src.sop_generator import render_draft_text

SOURCE = """Pump Maintenance
SAFETY WARNINGS
WARNING: Never open the pump casing while the motor is running.
CAUTION: Wear gloves when handling the drained fluid.
PROCEDURE
1. Switch off the pump motor at the local isolator.
2. Close the inlet valve and the outlet valve.
3. Drain the casing into the 20 litre waste container.
"""
W1 = "WARNING: Never open the pump casing while the motor is running."
W2 = "CAUTION: Wear gloves when handling the drained fluid."
S = ["Switch off the pump motor at the local isolator.", "Close the inlet valve and the outlet valve.",
     "Drain the casing into the 20 litre waste container."]


def step(n, text, sources, change="unchanged"):
    return {"id": f"R{n}", "text": text, "source_step_ids": sources, "change_type": change}


def unchanged_steps():
    return [step(n, text, [f"S{n}"]) for n, text in enumerate(S, start=1)]


def evaluate(steps=None, warnings=None, removed=(), request=""):
    structured = {
        "preamble": "Pump Maintenance",
        "steps": unchanged_steps() if steps is None else steps,
        "warnings": [{"id": "RW1", "text": W1, "source_warning_id": "W1"},
                     {"id": "RW2", "text": W2, "source_warning_id": "W2"}] if warnings is None else warnings,
        "removed_warning_ids": list(removed),
        "change_summary": "", "preserved_safety_requirements": "", "unresolved_questions": "",
        "source_limitations": "",
    }
    return evaluate_structured_revision(SOURCE, render_draft_text(structured), structured, request)


def of_type(result, kind):
    return [f for f in result["findings"] if f["type"] == kind]


def test_source_items_are_numbered_like_the_prompt():
    assert number_source_items(SOURCE) == ([("W1", W1), ("W2", W2)], [("S1", S[0]), ("S2", S[1]), ("S3", S[2])])


def test_faithful_structured_draft_passes():
    result = evaluate()
    assert result["status"] == "pass_automated", result["findings"]
    assert result["evaluator_version"] == EVALUATOR_VERSION + "+structured"
    assert result["metrics"]["matching"] == "structured" and result["metrics"]["warning_recall"] == 1.0


def test_warning_neither_carried_nor_removed_is_missing():
    result = evaluate(warnings=[{"id": "RW1", "text": W1, "source_warning_id": "W1"}])
    [finding] = of_type(result, "missing_warning")
    assert (finding["source_id"], finding["severity"], finding["source_line"]) == ("W2", "critical", 4)


def test_explicitly_removed_warning_is_still_critical():
    result = evaluate(warnings=[{"id": "RW1", "text": W1, "source_warning_id": "W1"}], removed=["W2"],
                      request="Remove the glove caution; the fluid is now drained automatically.")
    [finding] = of_type(result, "warning_removed")
    assert finding["severity"] == "critical" and result["status"] == "fail"
    assert result["metrics"]["removed_warnings"] == 1


def test_every_added_step_is_checked_against_every_warning():
    steps = unchanged_steps()[:2] + [
        step(3, "Open the pump casing while the motor is running to inspect the impeller.", [], "added"),
        step(4, S[2], ["S3"])]
    [finding] = of_type(evaluate(steps=steps), "contradicts_warning")
    assert (finding["source_id"], finding["draft_id"]) == ("W1", "R3")
    assert finding["draft_line"] == 6  # preamble, 2 warnings, then steps 1-3


def test_added_step_without_support_is_unsupported():
    steps = unchanged_steps() + [step(4, "Spray the floor with degreasing foam.", [], "added")]
    [finding] = of_type(evaluate(steps=steps), "unsupported_instruction")
    assert finding["draft_id"] == "R4"


def test_model_label_unchanged_is_not_trusted():
    steps = unchanged_steps()
    steps[1] = step(2, "Leave the inlet valve as it is and continue.", ["S2"], "unchanged")
    [finding] = of_type(evaluate(steps=steps), "altered_step")
    assert finding["detail"].startswith("Step is labelled unchanged") and finding["source_id"] == "S2"


def test_removed_and_unaccounted_steps():
    steps = unchanged_steps()
    steps[2] = step(3, S[2], ["S3"], "removed")
    [removed] = of_type(evaluate(steps=steps), "omitted_step")
    assert removed["severity"] == "critical"
    [requested] = of_type(evaluate(steps=steps, request="Remove the step that drains the casing into the waste container."), "omitted_step")
    assert requested["severity"] == "review"
    [lost] = of_type(evaluate(steps=unchanged_steps()[:2]), "omitted_step")
    assert lost["source_id"] == "S3" and lost["detail"].startswith("Source step is not accounted")


def test_order_uses_cited_ids():
    steps = [step(1, S[1], ["S2"]), step(2, S[0], ["S1"]), step(3, S[2], ["S3"])]
    assert of_type(evaluate(steps=steps), "step_order_violation")


def test_invalid_source_reference_is_flagged():
    steps = unchanged_steps()
    steps[0] = step(1, S[0], ["S1", "S9"])
    [finding] = of_type(evaluate(steps=steps), "invalid_source_reference")
    assert (finding["source_id"], finding["draft_id"], finding["severity"]) == ("S9", "R1", "review")


def test_requested_modification_and_value_pass():
    steps = unchanged_steps()
    steps[2] = step(3, "Drain the casing into the 35 litre waste container.", ["S3"], "modified")
    result = evaluate(steps=steps, request="Use the 35 litre waste container.")
    assert result["status"] == "pass_automated", result["findings"]
