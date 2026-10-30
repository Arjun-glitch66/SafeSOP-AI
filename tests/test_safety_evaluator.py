
from src.safety_evaluator import (
    warning_recall,
    warning_precision,
    unsupported_instruction_rate,
    order_integrity,
    evaluate_sop,
)


def test_all_warnings_preserved():
    original = ["Wear gloves", "Disconnect power"]
    generated = ["Wear gloves", "Disconnect power"]

    assert warning_recall(original, generated) == 1.0


def test_missing_warning_detected():
    original = ["Wear gloves", "Disconnect power"]
    generated = ["Wear gloves"]

    assert warning_recall(original, generated) == 0.5


def test_extra_warning_reduces_precision():
    required = ["Wear gloves"]
    generated = ["Wear gloves", "Use a special tool"]

    assert warning_precision(required, generated) == 0.5


def test_unsupported_instruction_rate():
    instructions = [
        {"text": "Check the machine", "supported": True},
        {"text": "Increase temperature to 200", "supported": False},
    ]

    assert unsupported_instruction_rate(instructions) == 0.5


def test_correct_step_order():
    required_pairs = [("isolate", "open")]
    generated_order = ["isolate", "verify", "open"]

    assert order_integrity(
        required_pairs, generated_order
    ) == 1.0


def test_incorrect_step_order():
    required_pairs = [("isolate", "open")]
    generated_order = ["open", "isolate"]

    assert order_integrity(
        required_pairs, generated_order
    ) == 0.0


def test_evaluator_flags_critical_failures():
    result = evaluate_sop(
        required_warnings=["Disconnect power"],
        generated_warnings=[],
        instructions=[
            {
                "text": "Open the machine immediately",
                "supported": False,
            }
        ],
        required_order_pairs=[("isolate", "open")],
        generated_order=["open", "isolate"],
    )

    assert result["status"] == "FAIL"
    assert len(result["findings"]) == 3


# --- Automated text-level evaluator (evaluate_revision) ---

from src.safety_evaluator import evaluate_revision  # noqa: E402

SOURCE = """Pump Maintenance
SAFETY WARNINGS
WARNING: Never open the pump casing while the motor is running.
PROCEDURE
1. Switch off the pump motor at the local isolator.
2. Close the inlet valve and the outlet valve.
3. Drain the casing into the 20 litre waste container.
"""


def draft(*steps, warning="WARNING: Never open the pump casing while the motor is running."):
    body = "\n".join(f"{n}. {s}" for n, s in enumerate(steps, start=1))
    return f"**DRAFT:**\n## Pump Maintenance\n**{warning}**\n{body}\n\nCHANGE SUMMARY:\n- none"


STEPS = [
    "Switch off the pump motor at the local isolator.",
    "Close the inlet valve and the outlet valve.",
    "Drain the casing into the 20 litre waste container.",
]


def finding_types(result):
    return {f["type"] for f in result["findings"] if f["severity"] != "info"}


def test_unchanged_markdown_draft_passes_automated_checks():
    result = evaluate_revision(SOURCE, draft(*STEPS))
    assert result["status"] == "pass_automated", result["findings"]
    assert result["metrics"]["warning_recall"] == 1.0
    assert result["metrics"]["order_integrity"] == 1.0


def test_missing_warning_fails():
    result = evaluate_revision(SOURCE, draft(*STEPS, warning="Be careful."))
    assert result["status"] == "fail"
    assert "missing_warning" in finding_types(result)


def test_swapped_steps_and_new_value_fail():
    swapped = [STEPS[1], STEPS[0], STEPS[2].replace("20", "35")]
    result = evaluate_revision(SOURCE, draft(*swapped))
    assert {"step_order_violation", "unsupported_value"} <= finding_types(result)


def test_value_from_change_request_is_allowed():
    changed = STEPS[:2] + [STEPS[2].replace("20", "35")]
    result = evaluate_revision(SOURCE, draft(*changed), "Use the 35 litre waste container.")
    assert "unsupported_value" not in finding_types(result)


def test_negated_step_is_a_conflict():
    negated = [STEPS[0], "Do not close the inlet valve and the outlet valve.", STEPS[2]]
    assert "conflicting_instruction" in finding_types(evaluate_revision(SOURCE, draft(*negated)))


def test_validation_set_standard_cases_all_correct():
    """Regression guard: every non-hard case in evaluation/testset.json must stay correct."""
    import json
    from pathlib import Path
    from evaluation.validate_evaluator import build_cases, COUNTED_SEVERITIES

    testset = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "testset.json").read_text())
    for case in build_cases(testset):
        if case["hard"]:
            continue
        result = evaluate_revision(case["original"], case["draft"], case["change_request"])
        detected = sorted({f["type"] for f in result["findings"] if f["severity"] in COUNTED_SEVERITIES})
        assert (detected, result["status"]) == (case["expected_types"], case["expected_status"]), case["case_id"]


def test_antonym_swap_is_a_conflict():
    flipped = [STEPS[0], "Open the inlet valve and the outlet valve.", STEPS[2]]
    result = evaluate_revision(SOURCE, draft(*flipped))
    assert result["status"] == "fail"
    assert "conflicting_instruction" in finding_types(result)


def test_antonym_requested_in_change_request_is_review_not_fail():
    flipped = [STEPS[0], "Open the inlet valve and the outlet valve.", STEPS[2]]
    result = evaluate_revision(SOURCE, draft(*flipped), "Keep the inlet valve open during draining.")
    conflicts = [f for f in result["findings"] if f["type"] == "conflicting_instruction"]
    assert conflicts and all(f["severity"] == "review" for f in conflicts)


def test_unit_change_with_same_number_is_flagged():
    changed = STEPS[:2] + [STEPS[2].replace("20 litre", "20 millilitre")]
    result = evaluate_revision(SOURCE, draft(*changed))
    assert any(f["type"] == "unsupported_value" and f["values"] == ["20 millilitre"] for f in result["findings"])


def test_merged_steps_are_not_an_order_violation():
    merged = [STEPS[0], "Close the inlet valve and the outlet valve, then drain the casing into the 20 litre waste container.", ]
    source = SOURCE.replace("2. Close the inlet valve and the outlet valve.", "2. Close the inlet valve.\n3. Close the outlet valve.").replace("3. Drain", "4. Drain")
    result = evaluate_revision(source, draft(*merged))
    assert "step_order_violation" not in finding_types(result)


def test_degree_unit_change_is_flagged():
    source = SOURCE.replace("3. Drain the casing", "3. Cool the casing to 40 °C, then drain it")
    changed = STEPS[:2] + ["Cool the casing to 40 °F, then drain it into the 20 litre waste container."]
    result = evaluate_revision(source, draft(*changed))
    assert any(f["type"] == "unsupported_value" and "40 fahrenheit" in f["values"] for f in result["findings"])


# --- v1.2 rules ---

from src.safety_evaluator import (  # noqa: E402
    check_change_applied, parse_prohibition, same_word, tokens,
)

LOCK_SOURCE = SOURCE.replace(
    "3. Drain the casing", "3. Each worker must apply a personal lock to the isolator.\n4. Drain the casing"
).replace("1. Switch off", "1. Notify all operators, then switch off")
LOCK_STEPS = [
    "Notify all operators, then switch off the pump motor at the local isolator.",
    STEPS[1],
    "Each worker must apply a personal lock to the isolator.",
    STEPS[2],
]


def findings_of(result, kind):
    return [f for f in result["findings"] if f["type"] == kind]


def test_v12_unchanged_lock_draft_passes():
    result = evaluate_revision(LOCK_SOURCE, draft(*LOCK_STEPS))
    assert result["status"] == "pass_automated", result["findings"]


def test_safety_words_are_no_longer_stopwords():
    assert {"all", "any", "each", "before", "after"} <= tokens("before any, after all, each")


def test_inserted_step_doing_the_forbidden_action_contradicts_the_warning():
    steps = STEPS[:2] + ["Open the pump casing while the motor is running to check the impeller."] + STEPS[2:]
    result = evaluate_revision(SOURCE, draft(*steps))
    [finding] = findings_of(result, "contradicts_warning")
    assert result["status"] == "fail" and finding["severity"] == "critical"
    assert finding["source"].startswith("WARNING: Never open the pump casing")
    assert (finding["source_line"], finding["draft_line"]) == (3, 5)  # quoted evidence is located


def test_no_contradiction_when_condition_absent_or_step_negated():
    for extra in ("Open the pump casing after the motor has stopped.",
                  "Do not open the pump casing while the motor is running."):
        steps = STEPS + [extra]
        assert not findings_of(evaluate_revision(SOURCE, draft(*steps)), "contradicts_warning"), extra


def test_parse_prohibition_and_stem_match():
    assert parse_prohibition("DANGER: Do not bypass the emergency stop circuit for any reason.") == (
        "bypass", {"emergency", "stop", "circuit"}, set())
    verb, action, condition = parse_prohibition("Never open the lid while the rotor is spinning.")
    assert (verb, action, condition) == ("open", {"lid"}, {"while", "rotor", "spinning"})
    assert parse_prohibition("Wear gloves.") is None
    assert same_word("bypass", "bypassing") and same_word("add", "adds") and not same_word("add", "address")


def test_quantifier_weakening_fails_and_requested_one_is_review():
    weakened = ["Notify most operators, then switch off the pump motor at the local isolator."] + LOCK_STEPS[1:]
    [finding] = findings_of(evaluate_revision(LOCK_SOURCE, draft(*weakened)), "quantifier_weakened")
    assert finding["severity"] == "critical" and finding["evidence"] == "'all' -> 'most'"
    [requested] = findings_of(evaluate_revision(LOCK_SOURCE, draft(*weakened), "Only notify most operators."),
                              "quantifier_weakened")
    assert requested["severity"] == "review"


def test_quantifier_strengthening_and_before_after_are_not_double_reported():
    source = SOURCE.replace("1. Switch off", "1. Before any work, switch off")
    stronger = ["Before all work, switch off the pump motor at the local isolator."] + STEPS[1:]
    assert not findings_of(evaluate_revision(source, draft(*stronger)), "quantifier_weakened")
    after = ["After any work, switch off the pump motor at the local isolator."] + STEPS[1:]
    result = evaluate_revision(source, draft(*after))
    assert findings_of(result, "conflicting_instruction") and not findings_of(result, "quantifier_weakened")


def test_actor_change_on_lock_step_is_high_and_fails():
    changed = LOCK_STEPS[:2] + ["The supervisor must apply a personal lock to the isolator."] + LOCK_STEPS[3:]
    result = evaluate_revision(LOCK_SOURCE, draft(*changed))
    [finding] = findings_of(result, "actor_changed")
    assert finding["severity"] == "high" and finding["evidence"] == "worker -> supervisor"
    assert result["status"] == "fail"


def test_actor_change_outside_lock_steps_is_ignored():
    source = SOURCE.replace("2. Close the inlet", "2. The operator closes the inlet")
    changed = [STEPS[0], "The technician closes the inlet valve and the outlet valve.", STEPS[2]]
    assert not findings_of(evaluate_revision(source, draft(*changed)), "actor_changed")


def test_change_not_applied():
    request = "Use the 35 litre waste container."
    assert findings_of(evaluate_revision(SOURCE, draft(*STEPS), request), "change_not_applied")  # 35 missing
    applied = STEPS[:2] + [STEPS[2].replace("20", "35")]
    assert not findings_of(evaluate_revision(SOURCE, draft(*applied), request), "change_not_applied")
    # A draft that equals the original fails even when the request has no new terms.
    [identical] = check_change_applied("Tidy the wording.", SOURCE, SOURCE)
    assert identical["detail"] == "The draft is identical to the original."


def test_change_check_skips_removals_and_empty_requests():
    removed = STEPS[:2]
    request = "Remove the draining step because the casing is now drained automatically."
    assert not findings_of(evaluate_revision(SOURCE, draft(*removed), request), "change_not_applied")
    assert check_change_applied("", SOURCE, SOURCE) == []
