"""Sections and steps of an extracted SOP, for section- and step-scoped revision.

Only the target part goes to the model; its revision is spliced back into the original
extracted text, so every other line passes through byte for byte.
ponytail: headings are found by shape (ALL-CAPS lines, or a short line ending in ':'), not by
PDF structure; SOPs with styled-but-lowercase headings show no sections and keep full/page scope.
"""
import re

from fastapi import HTTPException

from src.safety_evaluator import STEP_LINE, clean_line

HEADING = re.compile(r"^(?:[A-Z][A-Z0-9 &/,()'\-]{2,80}|[A-Z][^.:]{2,80}:)$")
PAGE_MARKER = re.compile(r"^\[PAGE \d+\]$")


def _is_heading(line):
    text = line.strip()
    return bool(text) and not PAGE_MARKER.match(text) and not STEP_LINE.match(clean_line(text)) \
        and bool(HEADING.match(text))


def outline(full_text):
    """Sections (SEC1..) and steps (S1..) with [start, end) line ranges in full_text.split('\\n')."""
    lines = full_text.split("\n")
    heading_rows = [i for i, line in enumerate(lines) if _is_heading(line)]
    sections = []
    for n, start in enumerate(heading_rows, start=1):
        end = heading_rows[n] if n < len(heading_rows) else len(lines)
        # A page marker or blank line just before the next heading stays outside the section.
        while end > start + 1 and (not lines[end - 1].strip() or PAGE_MARKER.match(lines[end - 1].strip())):
            end -= 1
        sections.append({"id": f"SEC{n}", "title": lines[start].strip(), "start": start, "end": end})

    steps = []
    for i, line in enumerate(lines):
        match = STEP_LINE.match(clean_line(line))
        if not match:
            continue
        end = i + 1  # a step continues on wrapped lines until a blank line, heading, marker or next step
        while end < len(lines) and lines[end].strip() and not _is_heading(lines[end]) \
                and not PAGE_MARKER.match(lines[end].strip()) and not STEP_LINE.match(clean_line(lines[end])):
            end += 1
        steps.append({"id": f"S{len(steps) + 1}", "number": match.group(1) or match.group(2),
                      "text": match.group(3).strip(), "start": i, "end": end})
    return sections, steps


def locate(full_text, scope, target):
    """The [start, end) line range and first step number of the target section or step."""
    sections, steps = outline(full_text)
    parts = {item["id"]: item for item in (sections if scope == "section" else steps)}
    if target not in parts:
        kind = "section" if scope == "section" else "step"
        available = ", ".join(parts) or "none detected"
        raise HTTPException(status_code=400, detail=f"Choose a {kind} that exists in this PDF ({available}).")
    part = parts[target]
    inside = [step for step in steps if part["start"] <= step["start"] < part["end"]]
    first_number = int(inside[0]["number"].split(".")[0]) if inside else 1
    return part["start"], part["end"], first_number


def part_text(full_text, start, end):
    return "\n".join(full_text.split("\n")[start:end])


def splice(full_text, start, end, revised_part):
    """The original text with lines [start, end) replaced; everything else unchanged."""
    lines = full_text.split("\n")
    return "\n".join(lines[:start] + revised_part.split("\n") + lines[end:])
