
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
