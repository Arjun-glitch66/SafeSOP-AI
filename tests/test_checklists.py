"""Required-element checklists (src/checklists/*.yaml)."""
from src.checklists import available_types, check_required_elements, load_packs
from src.safety_evaluator import evaluate_revision, text_lines

LOTO = """Conveyor Energy Isolation Procedure
WARNING: Never reach into the conveyor while the drive motor is energised.
1. Notify all affected operators that the conveyor will be shut down for maintenance.
2. Stop the conveyor using the normal stop button at the control panel.
3. Switch off the main isolator and confirm the isolator handle is in the off position.
4. Apply your personal lock and danger tag to the main isolator.
5. Release stored energy by slackening the belt tensioner screw.
6. Press the start button to verify that the conveyor does not move.
7. Remove locks and tags only after all personnel are clear of the conveyor.
"""


def draft_without(step_prefix):
    lines = [line for line in LOTO.splitlines() if not line.startswith(step_prefix)]
    return "DRAFT:\n" + "\n".join(lines)


def test_packs_load_and_every_pattern_compiles():
    packs = load_packs()
    assert {"lockout_tagout", "osha_operating_procedure"} <= set(packs)
    assert {p["id"] for p in available_types()} == set(packs)
    loto_ids = [e["id"] for e in packs["lockout_tagout"]["elements"]]
    assert loto_ids == ["notify", "shutdown", "isolation", "apply_locks_tags", "stored_energy", "verification", "remove_locks"]


def test_every_loto_element_is_found_in_a_complete_procedure():
    findings, metrics = check_required_elements("lockout_tagout", text_lines(LOTO), text_lines(LOTO))
    assert findings == [] and metrics["required_elements_in_source"] == 7
    assert metrics["required_elements_missing_in_source"] == []


def test_dropping_the_stored_energy_step_is_a_critical_missing_element():
    result = evaluate_revision(LOTO, draft_without("5."), "", document_type="lockout_tagout")
    [finding] = [f for f in result["findings"] if f["type"] == "missing_required_element"]
    assert finding["severity"] == "critical" and finding["evidence"] == "lockout_tagout.stored_energy"
    assert finding["source"].startswith("5. Release stored energy") and finding["source_line"] == 7
    assert result["status"] == "fail" and result["metrics"]["required_elements"]["required_elements_lost"] == 1


def test_elements_missing_from_the_original_are_reported_not_flagged():
    source = LOTO.replace("5. Release stored energy by slackening the belt tensioner screw.\n", "")
    findings, metrics = check_required_elements("lockout_tagout", text_lines(source), text_lines(source))
    assert findings == [] and metrics["required_elements_missing_in_source"] == ["stored_energy"]


def test_no_document_type_means_no_checklist():
    result = evaluate_revision(LOTO, draft_without("5."), "")
    assert result["metrics"]["required_elements"] is None
    assert not any(f["type"] == "missing_required_element" for f in result["findings"])


def test_osha_operating_procedure_pack_flags_a_lost_emergency_shutdown():
    source = ["Normal operations: keep the reactor between the upper and lower limits.",
              "Emergency shutdown: press the E-stop and close valve V-12.",
              "Wear PPE: goggles and gloves."]
    draft = [source[0], source[2]]
    findings, _ = check_required_elements("osha_operating_procedure", source, draft)
    assert [f["evidence"] for f in findings] == ["osha_operating_procedure.emergency_shutdown"]
