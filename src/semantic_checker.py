"""
Advisory semantic checker: does a draft step contradict a source warning in *meaning*?

The rule-based evaluator (safety_evaluator.py) compares words. This module asks a model instead,
to reach contradictions that use different words. It is advisory and one-way:

- it only ADDS findings (type `semantic_contradiction`, severity `review`, `advisory: True`);
- it can raise the status (pass_automated -> needs_review) but never lower it, so it can never
  turn a fail into a pass;
- if the backend fails, the evaluation is returned unchanged with the error recorded.

Selected by the environment variable SEMANTIC_CHECK = off (default) | nli | llm. Always off in CI.

  nli  A sentence-level NLI cross-encoder from Hugging Face (SEMANTIC_NLI_MODEL, default
       cross-encoder/nli-deberta-v3-small). Needs `pip install sentence-transformers`
       (pulls in torch). Runs locally; no data leaves the machine.
  llm  An LLM judge from a different provider than the generator (Gemini): Anthropic Claude
       (SEMANTIC_LLM_MODEL, default claude-opus-5-5). Needs `pip install anthropic` and
       ANTHROPIC_API_KEY. Sends the SOP warnings and draft steps to Anthropic; billed per call.
"""
import logging
import os
from functools import lru_cache

from pydantic import BaseModel

from src.safety_evaluator import extract_draft_section, extract_steps, extract_warnings

logger = logging.getLogger("safesop.semantic")

DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-small"
DEFAULT_LLM_MODEL = "claude-opus-5-5"
NLI_THRESHOLD = 0.8  # contradiction probability needed to report a pair
STATUS_RANK = {"pass_automated": 0, "needs_review": 1, "fail": 2}


def check(original_items, draft_items, backend):
    """Findings for draft items that a backend says contradict an original item.
    `backend.find_contradictions(original_items, draft_items)` returns
    [(original_item, draft_item, confidence 0-1, reason)]."""
    findings = []
    for original, draft, confidence, reason in backend.find_contradictions(original_items, draft_items):
        findings.append({
            "type": "semantic_contradiction", "severity": "review", "advisory": True,
            "detail": "Advisory (model-based): this draft step may contradict a source warning. "
                      "Not a rule finding; confirm by reading both.",
            "source": original, "draft": draft, "confidence": round(float(confidence), 3),
            "evidence": reason, "backend": backend.name,
        })
    return findings


class NliBackend:
    """Cross-encoder NLI: premise = source warning, hypothesis = draft step."""
    name = "nli"

    def __init__(self, model_name=None, threshold=NLI_THRESHOLD):
        self.model_name = model_name or os.getenv("SEMANTIC_NLI_MODEL", DEFAULT_NLI_MODEL)
        self.threshold = threshold

    def find_contradictions(self, original_items, draft_items):
        if not original_items or not draft_items:
            return []
        model = load_cross_encoder(self.model_name)
        labels = {name.lower(): index for index, name in model.config.id2label.items()}
        contradiction = labels.get("contradiction", 0)
        pairs = [(o, d) for o in original_items for d in draft_items]
        scores = model.predict(pairs, apply_softmax=True)
        return [(o, d, row[contradiction], f"NLI contradiction probability {row[contradiction]:.2f}")
                for (o, d), row in zip(pairs, scores) if row[contradiction] >= self.threshold]


@lru_cache(maxsize=2)
def load_cross_encoder(model_name):
    from sentence_transformers import CrossEncoder  # optional dependency, only for SEMANTIC_CHECK=nli
    return CrossEncoder(model_name)


class Contradiction(BaseModel):
    warning_index: int
    step_index: int
    confidence: float
    reason: str


class Judgement(BaseModel):
    contradictions: list[Contradiction]


JUDGE_PROMPT = """You check revised standard operating procedures for safety regressions.

Below are the safety warnings from the ORIGINAL procedure and the steps of a REVISED draft.
List every draft step that, if followed, would violate or weaken one of the warnings: it does
what a warning forbids, removes a condition the warning requires, or weakens who, when or how
much (for example "all" to "some", "before" to "after"). Ignore steps that merely mention the
same equipment without breaking the warning. If there are none, return an empty list.

Use the indices shown. confidence is 0 to 1. reason quotes the conflicting words.

WARNINGS:
{warnings}

DRAFT STEPS:
{steps}
"""


class LlmJudgeBackend:
    """LLM judge from a different provider than the generator, so it does not share its blind spots."""
    name = "llm"

    def __init__(self, model=None, client=None):
        self.model = model or os.getenv("SEMANTIC_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.client = client

    def find_contradictions(self, original_items, draft_items):
        if not original_items or not draft_items:
            return []
        if self.client is None:
            import anthropic  # optional dependency, only for SEMANTIC_CHECK=llm
            self.client = anthropic.Anthropic()
        prompt = JUDGE_PROMPT.format(
            warnings="\n".join(f"[{i}] {text}" for i, text in enumerate(original_items)),
            steps="\n".join(f"[{i}] {text}" for i, text in enumerate(draft_items)),
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
            output_format=Judgement,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"LLM judge returned no judgement (stop reason: {response.stop_reason}).")
        found = []
        for item in response.parsed_output.contradictions:
            if 0 <= item.warning_index < len(original_items) and 0 <= item.step_index < len(draft_items):
                found.append((original_items[item.warning_index], draft_items[item.step_index],
                              max(0.0, min(1.0, item.confidence)), item.reason))
        return found


BACKENDS = {"nli": NliBackend, "llm": LlmJudgeBackend}


def backend_from_env():
    mode = os.getenv("SEMANTIC_CHECK", "off").strip().lower()
    if mode in ("", "off"):
        return None
    if mode not in BACKENDS:
        raise ValueError(f"SEMANTIC_CHECK must be off, nli or llm (got '{mode}').")
    return BACKENDS[mode]()


def apply_semantic_check(evaluation, original_text, generated_text, backend=None):
    """Add advisory findings to a rule-based evaluation. Never removes findings or lowers status."""
    try:
        backend = backend or backend_from_env()
    except ValueError as exc:
        logger.error("%s", exc)
        return with_record(evaluation, {"status": "error", "message": str(exc)})
    if backend is None or "findings" not in evaluation:
        return evaluation

    draft, _ = extract_draft_section(generated_text)
    warnings = extract_warnings(original_text)
    steps = [step["text"] for step in extract_steps(draft)]
    try:
        advisory = check(warnings, steps, backend)
    except Exception as exc:  # advisory only: a backend failure must not lose or change the rule result
        logger.exception("Semantic check (%s) failed", backend.name)
        return with_record(evaluation, {"backend": backend.name, "status": "error",
                                        "message": f"{type(exc).__name__}: {exc}"})

    # Skip pairs the rules already reported as contradicting.
    known = {(f.get("source"), f.get("draft")) for f in evaluation["findings"] if f["type"] == "contradicts_warning"}
    advisory = [f for f in advisory if (f["source"], f["draft"]) not in known]
    status = evaluation["status"]
    if advisory and STATUS_RANK[status] < STATUS_RANK["needs_review"]:
        status = "needs_review"
    return {
        **with_record(evaluation, {"backend": backend.name, "status": "ran", "advisory_findings": len(advisory)}),
        "status": status,
        "findings": evaluation["findings"] + advisory,
    }


def with_record(evaluation, record):
    """Store what the semantic check did in the metrics, which the API saves with the evaluation."""
    return {**evaluation, "metrics": {**evaluation.get("metrics", {}), "semantic_check": record}}
