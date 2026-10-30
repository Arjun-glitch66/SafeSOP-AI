"""EXP-003 benchmark scaffolding: folder of SOPs, several models, draft-item annotation, kappa.
Gemini is stubbed; no network, no API key."""
import csv

import pytest

from evaluation import run_generation_experiment as runner
from evaluation.agreement import analyse_draft_items, draft_label

SOP_TEXT = """Pump Maintenance
SAFETY WARNINGS
WARNING: Never open the pump casing while the motor is running.
WARNING: Wear gloves and goggles when handling the drained fluid.
PROCEDURE
1. Switch off the pump motor at the local isolator.
2. Close the inlet valve and the outlet valve.
3. Drain the casing into the 20 litre waste container.
"""

# The stub "model" keeps the first warning, drops the second, changes the container size as
# requested, and adds a step that does what the first warning forbids.
DRAFT = """DRAFT:
Pump Maintenance
WARNING: Never open the pump casing while the motor is running.
1. Switch off the pump motor at the local isolator.
2. Close the inlet valve and the outlet valve.
3. Open the pump casing while the motor is running to check the impeller.
4. Drain the casing into the 30 litre waste container.

CHANGE SUMMARY:
- Container size changed.
"""


@pytest.fixture
def benchmark(tmp_path, monkeypatch):
    sop_dir = tmp_path / "benchmark"
    sop_dir.mkdir()
    (sop_dir / "pump.txt").write_text(SOP_TEXT, encoding="utf-8")
    with (sop_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "file", "change_request", "source_url", "licence"])
        writer.writerow(["PUMP-1", "pump.txt", "Use the 30 litre waste container.", "https://example.org/pump", "CC-BY"])

    calls = []

    def fake_generate_sop(original_text, change_request, output_scope, model):
        calls.append(model)
        return {"text": DRAFT, "model": model}

    monkeypatch.setattr(runner, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(runner, "generate_sop", fake_generate_sop)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    runner.main(["--experiment", "EXP-T", "--sop-dir", str(sop_dir), "--models", "model-a,model-b",
                 "--repeats", "1", "--pause", "0"])
    results = tmp_path / "results"
    read = lambda name: list(csv.DictReader((results / name).open(encoding="utf-8")))  # noqa: E731
    return {"calls": calls, "results": results, "annotation": read("EXP-T_annotation.csv"),
            "auto": read("EXP-T_auto_labels.csv"), "sources": read("EXP-T_source_items.csv")}


def test_runner_uses_every_sop_and_model_and_writes_blind_annotation(benchmark):
    assert benchmark["calls"] == ["model-a", "model-b"]
    annotation = benchmark["annotation"]
    assert {r["model"] for r in annotation} == {"model-a", "model-b"}
    # One row per DRAFT item (1 warning + 4 steps), no evaluator labels in the annotators' file.
    assert [r["draft_item_id"] for r in annotation if r["model"] == "model-a"] == ["D1", "D2", "D3", "D4", "D5"]
    assert not any("auto" in column for column in annotation[0])
    assert [s["item_id"] for s in benchmark["sources"]] == ["W1", "W2", "S1", "S2", "S3"]
    assert "model-a" in (benchmark["results"] / "EXP-T_generation.md").read_text(encoding="utf-8")


def test_auto_labels_mark_contradictions_and_omissions(benchmark):
    auto = {(r["model"], r["row_kind"], r["item_id"]): r for r in benchmark["auto"]}
    assert auto[("model-a", "draft", "D4")]["auto_label"] == "contradicting"   # inserted forbidden step
    assert auto[("model-a", "draft", "D2")]["auto_source_item"] == "S1"
    assert auto[("model-a", "source", "W2")]["auto_label"] == "omitted"        # dropped warning
    assert auto[("model-a", "source", "W1")]["auto_label"] == "kept"


def label(rows, labels):
    """labels: {draft_item_id: (label_a, source_a, label_b, source_b)} applied to model-a rows."""
    out = []
    for row in rows:
        if row["model"] == "model-a" and row["draft_item_id"] in labels:
            la, sa, lb, sb = labels[row["draft_item_id"]]
            row = {**row, "label_a": la, "source_item_a": sa, "label_b": lb, "source_item_b": sb}
        out.append(row)
    return out


def test_agreement_on_draft_items(benchmark):
    rows = label(benchmark["annotation"], {
        "D1": ("supported", "W1", "supported", "W1"),
        "D2": ("supported", "S1", "supported", "S1"),
        "D3": ("supported", "S2", "supported", "S2"),
        "D4": ("contradicting", "", "unsupported", ""),         # disagreement: excluded
        "D5": ("supported", "S3", "supported", "S3; W2"),        # B thinks it also covers W2
    })
    result = analyse_draft_items(rows, benchmark["auto"], benchmark["sources"])
    assert result["double_labelled"] == 5 and result["unresolved_disagreements"] == 1
    assert result["kappa"] == 0.444  # p_o = 4/5, p_e = (4*4)/25 = 0.64 -> (0.8 - 0.64) / 0.36
    assert result["mapping_agreement"] == 0.8
    assert result["false_alarm_rate"] == 0.0
    assert result["human_omissions"] == 0  # B mapped D5 to W2, so W2 counts as covered


def test_hallucination_omission_and_dangerous_miss(benchmark):
    rows = label(benchmark["annotation"], {
        "D1": ("supported", "W1", "supported", "W1"),
        "D2": ("unsupported", "", "unsupported", ""),            # humans: hallucinated, evaluator: supported
        "D3": ("supported", "S2", "supported", "S2"),
        "D4": ("contradicting", "", "contradicting", ""),
        "D5": ("supported", "S3", "supported", "S3"),
    })
    result = analyse_draft_items(rows, benchmark["auto"], benchmark["sources"])
    assert result["new_unsupported_items"] == 1
    assert result["per_label"]["contradicting"]["recall"] == 1.0
    assert [r["draft_item_id"] for r in result["dangerous_misses"]] == ["D2"]
    # Nobody mapped anything to W2 or S1: two human-found omissions; the evaluator caught W2 only.
    assert result["human_omissions"] == 2 and result["omission_recall"] == 0.5
    assert [o["item_id"] for o in result["missed_omissions"]] == ["S1"]


def test_unknown_draft_label_is_rejected():
    with pytest.raises(ValueError):
        draft_label("fine")
