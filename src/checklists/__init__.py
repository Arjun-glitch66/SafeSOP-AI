"""Required-element checklists per SOP type (YAML rule packs in this folder).

A pack lists the elements an SOP of that type must contain, each with regex patterns. The check
is regression-only: an element found in the original but not in the draft is a critical
`missing_required_element`. Elements the original already lacked are reported in the metrics,
not as findings, because the draft is not the place to discover gaps in the source.
ponytail: regex presence, not meaning; a reworded element can be missed (and is then flagged,
which errs on the side of review). Add patterns when reviewers mark such findings false alarms.
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

PACK_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_packs():
    packs = {}
    for path in sorted(PACK_DIR.glob("*.yaml")):
        pack = yaml.safe_load(path.read_text(encoding="utf-8"))
        for element in pack["elements"]:
            element["compiled"] = [re.compile(pattern, re.IGNORECASE) for pattern in element["patterns"]]
        packs[pack["id"]] = pack
    return packs


def available_types():
    return [{"id": pack["id"], "name": pack["name"], "reference": pack["reference"].strip()}
            for pack in load_packs().values()]


def first_match(element, lines):
    """(1-based line number, line) of the first line that shows this element, or None."""
    for number, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in element["compiled"]):
            return number, line
    return None


def check_required_elements(document_type, original_lines, draft_lines):
    """Findings and metrics for one pack. Unknown or empty document_type: nothing to check."""
    pack = load_packs().get(document_type or "")
    if not pack:
        return [], None
    findings, present, missing_in_source = [], 0, []
    for element in pack["elements"]:
        in_source = first_match(element, original_lines)
        if not in_source:
            missing_in_source.append(element["id"])
            continue
        present += 1
        if not first_match(element, draft_lines):
            number, line = in_source
            findings.append({
                "type": "missing_required_element", "severity": "critical",
                "detail": f"Required element '{element['name']}' ({pack['name']}) is in the original but not in the draft.",
                "source": line, "source_line": number, "draft": None, "draft_line": None,
                "evidence": f"{pack['id']}.{element['id']}",
            })
    metrics = {"checklist": pack["id"], "required_elements_in_source": present,
               "required_elements_missing_in_source": missing_in_source,
               "required_elements_lost": len(findings)}
    return findings, metrics
