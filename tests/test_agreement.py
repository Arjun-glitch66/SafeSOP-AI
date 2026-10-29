import pytest

from evaluation.agreement import analyse, cohens_kappa


def row(item_type, auto, a, b=""):
    return {"sop": "S", "repeat": "1", "item_type": item_type, "source_text": "t",
            "auto_label": auto, "human_label_a": a, "human_label_b": b}


def test_kappa_perfect_and_chance():
    assert cohens_kappa([("kept", "kept"), ("missing", "missing")]) == 1.0
    assert cohens_kappa([("kept", "missing"), ("missing", "kept")]) == -1.0


def test_dangerous_miss_and_disagreement_handling():
    rows = [
        row("warning", "preserved", "preserved", "preserved"),
        row("warning", "preserved", "missing", "missing"),   # evaluator missed a real problem
        row("step", "missing", "missing"),                   # single annotator is enough
        row("step", "present", "present", "altered"),        # disagreement -> excluded
    ]
    result = analyse(rows)
    assert result["unresolved_disagreements"] == 1
    assert result["judged"] == 3
    assert result["problem_recall"] == 0.5
    assert len(result["dangerous_misses"]) == 1
    assert result["per_type"]["warning"]["accuracy"] == 0.5


def test_unknown_label_is_rejected():
    with pytest.raises(ValueError):
        analyse([row("step", "present", "ok")])
