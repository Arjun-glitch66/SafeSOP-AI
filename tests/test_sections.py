"""Section and step outline, and splicing that leaves every other line untouched."""
import pytest
from fastapi import HTTPException

from app.services.sections import locate, outline, part_text, splice

TEXT = """[PAGE 1]
Pump Maintenance
SAFETY WARNINGS
WARNING: Never open the cover while the motor is running.
PROCEDURE
1. Switch off the motor at the isolator
   and confirm the isolator is locked.
2. Open the cover.
[PAGE 2]
Cleaning:
3. Wipe the rotor.
4. Close the cover."""
LINES = TEXT.split("\n")


def test_outline_finds_headings_and_wrapped_steps():
    sections, steps = outline(TEXT)
    assert [(s["id"], s["title"]) for s in sections] == [
        ("SEC1", "SAFETY WARNINGS"), ("SEC2", "PROCEDURE"), ("SEC3", "Cleaning:")]
    assert [(s["id"], s["number"]) for s in steps] == [("S1", "1"), ("S2", "2"), ("S3", "3"), ("S4", "4")]
    assert (steps[0]["start"], steps[0]["end"]) == (5, 7)  # the wrapped line belongs to step 1
    assert sections[1]["end"] == 8  # the [PAGE 2] marker before the next heading stays outside PROCEDURE


def test_locate_and_splice_change_only_the_target_section():
    start, end, first_step = locate(TEXT, "section", "SEC3")
    assert part_text(TEXT, start, end) == "Cleaning:\n3. Wipe the rotor.\n4. Close the cover."
    assert first_step == 3
    spliced = splice(TEXT, start, end, "Cleaning:\n3. Wipe the rotor with 70 percent ethanol.\n4. Close the cover.")
    assert spliced.split("\n")[:start] == LINES[:start]  # byte for byte
    assert spliced.endswith("3. Wipe the rotor with 70 percent ethanol.\n4. Close the cover.")


def test_step_scope_replaces_the_whole_wrapped_step_only():
    start, end, first_step = locate(TEXT, "step", "S1")
    assert part_text(TEXT, start, end).endswith("and confirm the isolator is locked.") and first_step == 1
    spliced = splice(TEXT, start, end, "1. Switch off and lock the isolator.").split("\n")
    assert spliced[:start] == LINES[:start] and spliced[start + 1:] == LINES[end:]


def test_unknown_target_lists_what_exists():
    with pytest.raises(HTTPException) as error:
        locate(TEXT, "section", "SEC9")
    assert error.value.status_code == 400 and "SEC1, SEC2, SEC3" in error.value.detail
