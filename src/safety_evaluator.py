
import re


def normalize_text(text):
    """Normalize text for simple, case-insensitive comparison."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def warning_recall(required_warnings, generated_warnings):
    """Calculate the proportion of required warnings preserved."""
    required = set(normalize_text(w) for w in required_warnings)
    generated = set(normalize_text(w) for w in generated_warnings)

    if not required:
        return 1.0

    preserved = required.intersection(generated)
    return len(preserved) / len(required)


def warning_precision(required_warnings, generated_warnings):
    """Calculate how many generated warnings match required warnings."""
    required = set(normalize_text(w) for w in required_warnings)
    generated = set(normalize_text(w) for w in generated_warnings)

    if not generated:
        return 1.0 if not required else 0.0

    correct = required.intersection(generated)
    return len(correct) / len(generated)


def unsupported_instruction_rate(instructions):
    """
    Instructions must be dictionaries containing:
    text: instruction text
    supported: True or False

    This function evaluates supplied support labels.
    It does not independently determine factual support.
    """
    if not instructions:
        return 0.0

    unsupported = sum(
        1 for item in instructions
        if item.get("supported") is False
    )

    return unsupported / len(instructions)


def order_integrity(required_pairs, generated_order):
    """
    required_pairs: list of (before_step_id, after_step_id)
    generated_order: list of step IDs in generated sequence
    """
    if not required_pairs:
        return 1.0

    positions = {
        step_id: index
        for index, step_id in enumerate(generated_order)
    }

    correct = 0

    for before, after in required_pairs:
        if before not in positions or after not in positions:
            continue

        if positions[before] < positions[after]:
            correct += 1

    return correct / len(required_pairs)


def evaluate_sop(
    required_warnings,
    generated_warnings,
    instructions,
    required_order_pairs,
    generated_order
):
    """Run the initial SAFE-SOP rule-based evaluation."""

    recall = warning_recall(
        required_warnings, generated_warnings
    )

    precision = warning_precision(
        required_warnings, generated_warnings
    )

    unsupported_rate = unsupported_instruction_rate(
        instructions
    )

    order_score = order_integrity(
        required_order_pairs, generated_order
    )

    findings = []

    # Conservative rule: every required warning must be retained.
    required_set = set(
        normalize_text(w) for w in required_warnings
    )
    generated_set = set(
        normalize_text(w) for w in generated_warnings
    )

    missing_warnings = required_set - generated_set

    if missing_warnings:
        findings.append({
            "type": "missing_warning",
            "severity": "critical",
            "details": sorted(missing_warnings)
        })

    unsupported = [
        item["text"]
        for item in instructions
        if item.get("supported") is False
    ]

    if unsupported:
        findings.append({
            "type": "unsupported_instruction",
            "severity": "critical",
            "details": unsupported
        })

    positions = {
        step_id: index
        for index, step_id in enumerate(generated_order)
    }

    order_violations = []

    for before, after in required_order_pairs:
        if (
            before not in positions
            or after not in positions
            or positions[before] >= positions[after]
        ):
            order_violations.append({
                "before": before,
                "after": after
            })

    if order_violations:
        findings.append({
            "type": "step_order_violation",
            "severity": "critical",
            "details": order_violations
        })

    status = "FAIL" if findings else "PASS"

    return {
        "status": status,
        "metrics": {
            "warning_recall": round(recall, 4),
            "warning_precision": round(precision, 4),
            "unsupported_instruction_rate": round(
                unsupported_rate, 4
            ),
            "critical_order_integrity": round(
                order_score, 4
            )
        },
        "findings": findings
    }
