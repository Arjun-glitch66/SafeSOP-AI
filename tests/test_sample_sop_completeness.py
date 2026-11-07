"""Regression: the two-page sample SOP (tests/fixtures/Sample_SOP_Water_Transfer_Pump_Flushing.pdf).

A live prompt-v5 run on this PDF changed 5 -> 10 litres correctly but left out sections 7-9
(Acceptance checks, Records, Revision history): the v5 schema had no place for text after the
procedure. The evaluator also reported headings and the training disclaimer as missing although
they were in the draft: numbered headings ("1. Purpose") were read as procedure steps, and the
disclaimer was cut at its PDF line wrap. Fictional training document; Gemini is faked here.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.pdf import extract_document_text
from app.services.sections import outline
from src import sop_generator
from src.safety_evaluator import (
    evaluate_revision,
    evaluate_structured_revision,
    extract_headings,
    number_source_items,
    text_lines,
)

SAMPLE = Path(__file__).parent / "fixtures" / "Sample_SOP_Water_Transfer_Pump_Flushing.pdf"
REQUEST = "Change the example flush quantity in step 6 from 5 litres to 10 litres."
HEADINGS = ["Purpose", "Scope", "Responsibilities", "Required items", "Safety notes",
            "Procedure - Training Sequence", "Acceptance checks", "Records", "Revision history"]


@pytest.fixture(scope="module")
def source():
    text, page = extract_document_text(str(SAMPLE), "full", None)
    assert page is None and text.count("[PAGE ") == 2
    return text


def sample_draft(source, *, closing=True, disclaimer_listed=True):
    """A structured draft laid out as prompt v6 asks: every section kept, only step 6 changed."""
    lines = [line for line in text_lines(source) if not line.startswith(("[PAGE", "TRAINING SAMPLE - NOT"))]
    warnings, steps = number_source_items(source)
    warning_texts = {text for _, text in warnings}
    step_texts = [text for _, text in steps]
    procedure = lines.index("6. Procedure - Training Sequence")
    last_step = max(i for i, line in enumerate(lines) if any(line.endswith(text) for text in step_texts[-1:]))
    preamble = [line for line in lines[:procedure] if line not in warning_texts]
    listed = warnings if disclaimer_listed else warnings[1:]
    if not disclaimer_listed:
        preamble.insert(3, warnings[0][1])
    draft_steps = [{"id": f"R{n}", "text": text, "source_step_ids": [f"S{n}"], "change_type": "unchanged", "reason": ""}
                   for n, text in enumerate(step_texts, start=1)]
    draft_steps[5] = {**draft_steps[5], "text": step_texts[5].replace("5 litres", "10 litres"),
                      "change_type": "modified", "reason": "The change request sets the example quantity to 10 litres."}
    return {
        "preamble": "\n".join(preamble),
        "procedure_intro": lines[procedure],
        "steps": draft_steps,
        "closing": "\n".join(lines[last_step + 1:]) if closing else "",
        "warnings": [{"id": f"RW{n}", "text": text, "source_warning_id": wid, "reason": ""}
                     for n, (wid, text) in enumerate(listed, start=1)],
        "removed_warning_ids": [],
        "change_summary": "Step 6: 5 litres -> 10 litres.",
        "preserved_safety_requirements": "All warnings and the training disclaimer.",
        "unresolved_questions": "None.",
        "source_limitations": "None.",
    }


def evaluate(source, draft):
    return evaluate_structured_revision(source, sop_generator.render_draft_text(draft), draft, REQUEST)


def types_of(result, *kinds):
    return [f for f in result["findings"] if f["type"] in kinds]


# --- parsing the source ---

def test_sample_pdf_parses_into_sections_whole_warnings_and_the_eight_steps(source):
    warnings, steps = number_source_items(source)
    assert extract_headings(source) == HEADINGS
    assert [text for _, text in steps][0].startswith("Review the training checklist")
    assert len(steps) == 8  # headings are no longer steps S1-S6 and S15-S17
    assert steps[5][1].endswith("not an instruction to operate a pump.")  # the wrapped line is joined
    assert steps[6][1].endswith("remains stable.")
    disclaimer = warnings[0][1]
    assert disclaimer.startswith("TRAINING SAMPLE ONLY.") and disclaimer.endswith("Do not use it to operate equipment.")
    assert [text.split(":")[0] for _, text in warnings[1:]] == ["WARNING", "CAUTION"]


def test_section_and_step_pickers_use_the_same_numbering(source):
    sections, steps = outline(source)
    titles = [section["title"].strip() for section in sections]
    assert [f"{n}. {heading}" for n, heading in enumerate(HEADINGS, start=1)] == titles[1:]
    assert [step["id"] for step in steps] == [step_id for step_id, _ in number_source_items(source)[1]]
    assert steps[5]["end"] - steps[5]["start"] == 2  # step 6 and its wrapped line go to the model together


def test_short_steps_between_neighbours_stay_steps():
    text = "Pump check\n1. Close valve\n2. Open drain valve\n3. Check gauge\n"
    assert [step_id for step_id, _ in number_source_items(text)[1]] == ["S1", "S2", "S3"]
    assert extract_headings(text) == []


# --- the prompt ---

def test_prompt_lists_every_section_and_asks_for_a_complete_document(source):
    prompt = sop_generator.build_sop_prompt(source, REQUEST, boundary="b" * 32)
    block = prompt.split(f"<<<SOURCE SECTIONS {'b' * 32}>>>")[1].split("<<<END")[0]
    assert block.split() == " ".join(HEADINGS).split()
    rules = sop_generator.build_system_instruction("b" * 32)
    for words in ("closing:", "acceptance checks", "revision history", "Never drop, merge or summarise a section"):
        assert words in rules
    assert sop_generator.PROMPT_VERSION == "v6"


# --- the evaluator on drafts of this sample ---

def test_a_complete_draft_has_no_missing_section_warning_or_step(source):
    draft = sample_draft(source)
    text = sop_generator.render_draft_text(draft)
    for kept in ("7. Acceptance checks", "8. Records", "9. Revision history", "P-101 label matches the training record",
                 "Initial fictional sample for software testing", "End of training sample."):
        assert kept in text
    result = evaluate(source, draft)
    assert not types_of(result, "omitted_section", "section_content_missing", "missing_warning",
                        "omitted_step", "warning_not_listed")
    assert result["metrics"]["section_coverage"] == 1.0 and result["metrics"]["source_sections"] == 9
    assert result["metrics"]["warning_recall"] == 1.0 and result["metrics"]["step_coverage"] == 1.0
    assert result["status"] != "fail"
    body = text.split("CHANGE SUMMARY:")[0]
    assert "10 litres" in body and "5 litres" not in body
    plain = evaluate_revision(source, text, REQUEST)  # the text-only path agrees
    assert not types_of(plain, "omitted_section", "missing_warning", "omitted_step")


def test_the_v5_failure_dropping_sections_7_to_9_fails_the_draft(source):
    result = evaluate(source, sample_draft(source, closing=False))
    omitted = types_of(result, "omitted_section")
    assert [f["source"] for f in omitted] == ["7. Acceptance checks", "8. Records", "9. Revision history"]
    assert {f["severity"] for f in omitted} == {"high"} and result["status"] == "fail"
    assert result["metrics"]["omitted_sections"] == 3


def test_a_disclaimer_kept_in_the_text_is_not_reported_missing_but_is_still_reviewed(source):
    result = evaluate(source, sample_draft(source, disclaimer_listed=False))
    assert not types_of(result, "missing_warning")
    [finding] = types_of(result, "warning_not_listed")
    assert finding["severity"] == "review" and finding["source"].startswith("TRAINING SAMPLE ONLY.")
    # Dropping it for real is still a critical finding: the check is not weakened.
    dropped = sample_draft(source, disclaimer_listed=False)
    dropped["preamble"] = dropped["preamble"].replace(finding["source"], "")
    assert [f["severity"] for f in types_of(evaluate(source, dropped), "missing_warning")] == ["critical"]


def test_a_heading_on_the_same_line_as_its_text_counts_as_present(source):
    draft = sample_draft(source)
    draft["preamble"] = draft["preamble"].replace("1. Purpose\n", "1. Purpose: ").replace("2. Scope\n", "2. Scope - ")
    assert "1. Purpose: Describe a controlled" in sop_generator.render_draft_text(draft)
    assert not types_of(evaluate(source, draft), "omitted_section", "section_content_missing")


def test_a_note_moved_to_another_section_is_flagged_for_review(source):
    # The live v6 run put the Safety notes NOTE under the procedure heading. It is in the draft, but
    # not in its section, so a reviewer is asked to confirm; it does not fail the draft.
    draft = sample_draft(source)
    note = next(line for line in draft["preamble"].split("\n") if line.startswith("NOTE:"))
    draft["preamble"] = draft["preamble"].replace(note + "\n", "").replace("\n" + note, "")
    draft["procedure_intro"] += "\n" + note
    [finding] = types_of(evaluate(source, draft), "section_content_missing")
    assert finding["severity"] == "review" and finding["source"] == "5. Safety notes"


# --- the generator asks again for an incomplete draft ---

def fake(parsed):
    usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
    return SimpleNamespace(parsed=parsed, text="", usage_metadata=usage)


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.delenv("GEMINI_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_FALLBACK_PROVIDER", raising=False)
    answers, calls = [], []

    def generate_content(**kwargs):
        calls.append(kwargs)
        return answers[len(calls) - 1]

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(sop_generator.genai, "Client", lambda **kwargs: client)
    return answers, calls


def test_a_draft_missing_sections_is_asked_for_again(source, gemini):
    answers, calls = gemini
    answers += [fake(sop_generator.SopDraft(**sample_draft(source, closing=False))),
                fake(sop_generator.SopDraft(**sample_draft(source)))]
    result = sop_generator.generate_sop(source, REQUEST)
    assert len(calls) == 2
    assert "8. Records" in result["text"] and "9. Revision history" in result["text"]
    assert result["structured"]["closing"]  # the second, complete answer is the one returned


def test_if_every_attempt_is_incomplete_the_draft_is_kept_and_fails_evaluation(source, gemini):
    answers, calls = gemini
    answers += [fake(sop_generator.SopDraft(**sample_draft(source, closing=False)))] * 2
    result = sop_generator.generate_sop(source, REQUEST)
    assert len(calls) == 2 and result["fallback_used"] is False
    assert "8. Records" not in result["text"]
    evaluation = evaluate_structured_revision(source, result["text"], result["structured"], REQUEST)
    assert evaluation["status"] == "fail" and evaluation["metrics"]["omitted_sections"] == 3
