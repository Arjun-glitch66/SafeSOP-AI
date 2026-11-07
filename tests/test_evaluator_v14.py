"""Evaluator v1.4: signal-word downgrades, changed values, unexplained changes, warning precision
and lexical consistency, on both the text path and the structured (prompt v5) path."""
from src.safety_evaluator import EVALUATOR_VERSION, evaluate_revision, evaluate_structured_revision
from src.sop_generator import render_draft_text

SOURCE = """Oven Curing Procedure
SAFETY WARNINGS
DANGER: Do not open the oven door while the heaters are energised.
WARNING: Wear heat resistant gloves when removing the rack.
PROCEDURE
1. Preheat the oven for 10 minutes.
2. Load the parts and close the door.
3. Cure the parts for 30 minutes.
4. Let the parts cool for 10 minutes before handling.
"""
WARNINGS = ["DANGER: Do not open the oven door while the heaters are energised.",
            "WARNING: Wear heat resistant gloves when removing the rack."]
STEPS = ["Preheat the oven for 10 minutes.", "Load the parts and close the door.",
         "Cure the parts for 30 minutes.", "Let the parts cool for 10 minutes before handling."]


def draft(warnings=WARNINGS, steps=STEPS):
    body = "\n".join(["Oven Curing Procedure", *warnings, *[f"{n}. {s}" for n, s in enumerate(steps, start=1)]])
    return f"DRAFT:\n{body}\n\nCHANGE SUMMARY:\n- none"


def types(result):
    return [f["type"] for f in result["findings"]]


def test_version_tag():
    assert EVALUATOR_VERSION == "safe-sop-eval-1.5"


def test_an_unchanged_draft_with_a_request_only_fails_change_applied():
    result = evaluate_revision(SOURCE, draft(), "")
    assert result["status"] == "pass_automated", result["findings"]
    assert result["metrics"]["warning_precision"] == 1.0
    assert result["metrics"]["lexical_consistency"] == 1.0


# ---- signal words ----

def test_danger_lowered_to_caution_fails():
    result = evaluate_revision(SOURCE, draft([WARNINGS[0].replace("DANGER", "CAUTION"), WARNINGS[1]]))
    found = [f for f in result["findings"] if f["type"] == "warning_downgraded"]
    assert len(found) == 1 and found[0]["severity"] == "high" and found[0]["evidence"] == "DANGER -> CAUTION"
    assert found[0]["source_line"] == 3 and found[0]["draft_line"] == 2
    assert result["status"] == "fail" and result["metrics"]["downgraded_warnings"] == 1


def test_a_requested_downgrade_is_review_and_a_raised_signal_word_is_fine():
    lowered = evaluate_revision(SOURCE, draft([WARNINGS[0], WARNINGS[1].replace("WARNING", "CAUTION")]),
                                "Reclassify the glove statement as a caution.")
    assert [f["severity"] for f in lowered["findings"] if f["type"] == "warning_downgraded"] == ["review"]
    raised = evaluate_revision(SOURCE, draft([WARNINGS[0], WARNINGS[1].replace("WARNING", "DANGER")]))
    assert "warning_downgraded" not in types(raised)


def test_a_dropped_label_is_review():
    result = evaluate_revision(SOURCE, draft([WARNINGS[0].replace("DANGER: ", ""), WARNINGS[1]]))
    assert [f["severity"] for f in result["findings"] if f["type"] == "warning_downgraded"] == ["review"]


# ---- changed values (the gap the v1.1 unit check leaves) ----

def test_a_value_changed_to_another_source_value_with_the_same_unit_fails():
    # 30 -> 10 minutes: 10 minutes is already in the source, so unsupported_value cannot see it.
    result = evaluate_revision(SOURCE, draft(steps=[*STEPS[:2], "Cure the parts for 10 minutes.", STEPS[3]]))
    assert "unsupported_value" not in types(result)
    found = [f for f in result["findings"] if f["type"] == "value_changed"]
    assert len(found) == 1 and found[0]["severity"] == "critical" and found[0]["evidence"] == "30 -> 10 minute"
    assert result["status"] == "fail" and result["metrics"]["changed_values"] == 1


def test_a_value_the_change_request_gives_is_not_flagged():
    result = evaluate_revision(SOURCE, draft(steps=[*STEPS[:2], "Cure the parts for 10 minutes.", STEPS[3]]),
                               "Shorten the cure to 10 minutes.")
    assert "value_changed" not in types(result)


def test_a_value_requested_with_another_unit_is_still_flagged():
    # The request gives 10 for a different quantity (bar); 10 minutes for the cure is not what it asked.
    result = evaluate_revision(SOURCE, draft(steps=[*STEPS[:2], "Cure the parts for 10 minutes.", STEPS[3]]),
                               "Set the air supply to 10 bar.")
    assert "value_changed" in types(result)


def test_a_new_number_is_left_to_unsupported_value():
    result = evaluate_revision(SOURCE, draft(steps=[*STEPS[:2], "Cure the parts for 45 minutes.", STEPS[3]]))
    assert "unsupported_value" in types(result) and "value_changed" not in types(result)


def test_unitless_values():
    source = "PROCEDURE\n1. Use 4 clamps on the frame.\n2. Check 2 gauges on the panel.\n"
    result = evaluate_revision(source, "DRAFT:\nPROCEDURE\n1. Use 2 clamps on the frame.\n2. Check 2 gauges on the panel.")
    assert "value_changed" in types(result)


# ---- warning precision ----

def test_warning_precision_counts_draft_warnings_without_support():
    invented = "CAUTION: Ensure the extraction fan is running at all times during curing."
    result = evaluate_revision(SOURCE, draft([*WARNINGS, invented]))
    assert result["metrics"]["draft_warnings"] == 3
    assert result["metrics"]["warning_precision"] == round(2 / 3, 4)
    supported = evaluate_revision(SOURCE, draft([*WARNINGS, invented]), "Add: ensure the extraction fan is running.")
    assert supported["metrics"]["warning_precision"] == 1.0


def test_lexical_consistency_drops_when_matched_steps_are_reworded():
    # Averaged over matched pairs only; a step reworded beyond matching counts against step_coverage instead.
    reworded = evaluate_revision(SOURCE, draft(steps=[STEPS[0], "Load the parts and shut the door.", *STEPS[2:]]))
    assert reworded["metrics"]["lexical_consistency"] < 1.0


# ---- structured path (prompt v5 reasons) ----

def structured(steps, warnings=None):
    data = {
        "preamble": "Oven Curing Procedure",
        "warnings": warnings if warnings is not None else [
            {"id": "RW1", "text": WARNINGS[0], "source_warning_id": "W1", "reason": ""},
            {"id": "RW2", "text": WARNINGS[1], "source_warning_id": "W2", "reason": ""}],
        "steps": steps, "removed_warning_ids": [], "change_summary": "", "preserved_safety_requirements": "",
        "unresolved_questions": "", "source_limitations": "",
    }
    return data


def step(n, text, change="unchanged", reason=""):
    return {"id": f"R{n}", "text": text, "source_step_ids": [f"S{n}"], "change_type": change, "reason": reason}


def run(data, request="Load the parts on the lower shelf."):
    return evaluate_structured_revision(SOURCE, render_draft_text(data), data, request)


def test_a_change_without_a_reason_is_flagged_for_review():
    steps = [step(1, STEPS[0]), step(2, "Load the parts on the lower shelf and close the door.", "modified"),
             step(3, STEPS[2]), step(4, STEPS[3])]
    result = run(structured(steps))
    found = [f for f in result["findings"] if f["type"] == "unexplained_change"]
    assert len(found) == 1 and found[0]["severity"] == "review" and found[0]["draft_id"] == "R2"
    assert result["metrics"]["unexplained_changes"] == 1
    steps[1]["reason"] = "The change request moves loading to the lower shelf."
    explained = run(structured(steps))
    assert "unexplained_change" not in types(explained) and explained["metrics"]["unexplained_changes"] == 0


def test_a_new_warning_needs_a_reason_and_older_drafts_without_reasons_are_not_flagged():
    warnings = [{"id": "RW1", "text": WARNINGS[0], "source_warning_id": "W1", "reason": ""},
                {"id": "RW2", "text": WARNINGS[1], "source_warning_id": "W2", "reason": ""},
                {"id": "RW3", "text": "CAUTION: The lower shelf is hotter than the upper shelf.",
                 "source_warning_id": None, "reason": ""}]
    steps = [step(n, text) for n, text in enumerate(STEPS, start=1)]
    assert "unexplained_change" in types(run(structured(steps, warnings)))
    legacy = structured([{k: v for k, v in s.items() if k != "reason"} for s in steps],
                        [{k: v for k, v in w.items() if k != "reason"} for w in warnings])
    assert "unexplained_change" not in types(run(legacy))


def test_structured_signal_word_and_value_checks():
    steps = [step(1, STEPS[0]), step(2, STEPS[1]), step(3, "Cure the parts for 10 minutes.", "modified", "faster"),
             step(4, STEPS[3])]
    warnings = [{"id": "RW1", "text": WARNINGS[0].replace("DANGER", "WARNING"), "source_warning_id": "W1", "reason": "x"},
                {"id": "RW2", "text": WARNINGS[1], "source_warning_id": "W2", "reason": ""}]
    result = run(structured(steps, warnings))
    assert {"warning_downgraded", "value_changed"} <= set(types(result))
    assert result["status"] == "fail"
    assert result["metrics"]["lexical_consistency"] is not None
