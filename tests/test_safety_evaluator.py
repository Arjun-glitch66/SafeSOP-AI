
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
