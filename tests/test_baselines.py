"""EXP-004 baselines behave as documented."""
from evaluation import baselines

ORIGINAL = "SAFETY WARNINGS\nWARNING: Never open the lid while the rotor is spinning.\nPROCEDURE\n1. Close the lid.\n2. Start the run."


def case(draft_body, expected="pass_automated", group="standard"):
    return {"original": ORIGINAL, "draft": "DRAFT:\n" + draft_body, "change_request": "", "expected_status": expected,
            "group": group}


def test_exact_warning_only_sees_verbatim_loss():
    assert baselines.exact_warning(case(ORIGINAL)) == "pass_automated"
    assert baselines.exact_warning(case(ORIGINAL.replace("Never", "Do not"))) == "fail"
    swapped = "SAFETY WARNINGS\nWARNING: Never open the lid while the rotor is spinning.\nPROCEDURE\n1. Start the run.\n2. Close the lid."
    assert baselines.exact_warning(case(swapped)) == "pass_automated"  # an order swap is invisible to it


def test_similarity_and_summary():
    assert baselines.text_similarity(case(ORIGINAL)) == "pass_automated"
    assert baselines.text_similarity(case("Something else entirely.")) == "fail"
    cases = [case(ORIGINAL), case("x", expected="fail")]
    summary = baselines.summarise(cases, ["pass_automated", "needs_review"])
    assert summary["flag_accuracy"] == 1.0 and summary["status_accuracy"] == 0.5
    assert summary["defects_flagged"] == 1.0 and summary["clean_false_alarms"] == 0.0
