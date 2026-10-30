
import os
import re


def normalize_text(text):
    """Normalize text for simple, case-insensitive comparison."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def warning_recall(required_warnings, generated_warnings):
    """Calculate the proportion of required warnings preserved."""
    required = set(normalize_text(w) for w in required_warnings)
    generated = set(normalize_text(w) for w in generated_warnings)

    if not required:
        return 1.0

    preserved = required.intersection(generated)
    return len(preserved) / len(required)


def warning_precision(required_warnings, generated_warnings):
    """Calculate how many generated warnings match required warnings."""
    required = set(normalize_text(w) for w in required_warnings)
    generated = set(normalize_text(w) for w in generated_warnings)

    if not generated:
        return 1.0 if not required else 0.0

    correct = required.intersection(generated)
    return len(correct) / len(generated)


def unsupported_instruction_rate(instructions):
    """
    Instructions must be dictionaries containing:
    text: instruction text
    supported: True or False

    This function evaluates supplied support labels.
    It does not independently determine factual support.
    """
    if not instructions:
        return 0.0

    unsupported = sum(
        1 for item in instructions
        if item.get("supported") is False
    )

    return unsupported / len(instructions)


def order_integrity(required_pairs, generated_order):
    """
    required_pairs: list of (before_step_id, after_step_id)
    generated_order: list of step IDs in generated sequence
    """
    if not required_pairs:
        return 1.0

    positions = {
        step_id: index
        for index, step_id in enumerate(generated_order)
    }

    correct = 0

    for before, after in required_pairs:
        if before not in positions or after not in positions:
            continue

        if positions[before] < positions[after]:
            correct += 1

    return correct / len(required_pairs)


def evaluate_sop(
    required_warnings,
    generated_warnings,
    instructions,
    required_order_pairs,
    generated_order
):
    """Run the initial SAFE-SOP rule-based evaluation."""

    recall = warning_recall(
        required_warnings, generated_warnings
    )

    precision = warning_precision(
        required_warnings, generated_warnings
    )

    unsupported_rate = unsupported_instruction_rate(
        instructions
    )

    order_score = order_integrity(
        required_order_pairs, generated_order
    )

    findings = []

    # Conservative rule: every required warning must be retained.
    required_set = set(
        normalize_text(w) for w in required_warnings
    )
    generated_set = set(
        normalize_text(w) for w in generated_warnings
    )

    missing_warnings = required_set - generated_set

    if missing_warnings:
        findings.append({
            "type": "missing_warning",
            "severity": "critical",
            "details": sorted(missing_warnings)
        })

    unsupported = [
        item["text"]
        for item in instructions
        if item.get("supported") is False
    ]

    if unsupported:
        findings.append({
            "type": "unsupported_instruction",
            "severity": "critical",
            "details": unsupported
        })

    positions = {
        step_id: index
        for index, step_id in enumerate(generated_order)
    }

    order_violations = []

    for before, after in required_order_pairs:
        if (
            before not in positions
            or after not in positions
            or positions[before] >= positions[after]
        ):
            order_violations.append({
                "before": before,
                "after": after
            })

    if order_violations:
        findings.append({
            "type": "step_order_violation",
            "severity": "critical",
            "details": order_violations
        })

    status = "FAIL" if findings else "PASS"

    return {
        "status": status,
        "metrics": {
            "warning_recall": round(recall, 4),
            "warning_precision": round(precision, 4),
            "unsupported_instruction_rate": round(
                unsupported_rate, 4
            ),
            "critical_order_integrity": round(
                order_score, 4
            )
        },
        "findings": findings
    }


# ---------------------------------------------------------------------------
# Automated text-level evaluation (SAFE-SOP framework v1.2).
# Compares a generated draft against the immutable original SOP text without
# hand-made labels. Definitions, thresholds and limitations are documented in
# research_logbook/EVALUATION_FRAMEWORK.md. Keep both in sync.
# ---------------------------------------------------------------------------

# Earlier versions are reproducible from git: each results/evaluator_validation_<version>*.json
# records the commit it ran on.
EVALUATOR_VERSION = "safe-sop-eval-1.2"

MATCH_THRESHOLD = 0.8      # at or above: preserved / matched
PARTIAL_THRESHOLD = 0.5    # between partial and match: altered, needs review
DUPLICATE_THRESHOLD = 0.9  # two draft steps this similar are duplicates

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "by",
    "with", "from", "is", "are", "be", "been", "this", "that", "it", "its",
    "as", "into", "then", "until",
    "warning", "caution", "danger", "note", "step",
}
# v1.2: all, any, each, before and after are no longer stop-words. They carry safety
# meaning ("after all personnel are clear"); every, only, never and not never were.
NEGATIONS = {"not", "never", "no", "dont", "cannot", "nor"}
WARNING_LINE = re.compile(
    r"\b(warning|caution|danger|hazard|do not|don't|never|must not|emergency|"
    r"lockout|tagout|ppe|protective)\b",
    re.IGNORECASE,
)
STEP_LINE = re.compile(r"^(?:step\s+(\d+)[.):]?|(\d+(?:\.\d+)*)[.)])\s+(.+)$", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
DRAFT_SECTION = re.compile(
    r"DRAFT:\s*(.*?)(?=^\s*CHANGE SUMMARY:|\Z)", re.IGNORECASE | re.DOTALL | re.MULTILINE
)

# "high" (v1.2) fails a draft like "critical"; it marks findings that are serious but rest on a
# rougher heuristic (who performs a step), so a reviewer reads them after the critical ones.
SEVERITY_ORDER = {"critical": 0, "high": 1, "review": 2, "info": 3}
FAILING_SEVERITIES = {"critical", "high"}

# v1.1: opposite-meaning word pairs. Swapping one for the other keeps almost every
# token, so token overlap alone cannot see it (EXP-001 HARD-ANTONYM).
# ponytail: fixed list, not semantic; extend it when annotation finds new pairs.
ANTONYMS = [
    ("on", "off"), ("open", "close"), ("opened", "closed"), ("raise", "lower"),
    ("raised", "lowered"), ("start", "stop"), ("before", "after"), ("tighten", "loosen"),
    ("increase", "decrease"), ("enable", "disable"), ("connect", "disconnect"),
    ("lock", "unlock"), ("above", "below"), ("minimum", "maximum"), ("engage", "disengage"),
]

# v1.1: units checked together with their number (EXP-001 HARD-UNIT: 3000 rpm -> 3000 rcf).
# Single-letter units (m, g, l, s) are left out because they are ambiguous in prose.
UNIT_WORDS = {
    "nm", "psi", "bar", "kpa", "mpa", "mm", "cm", "km", "metre", "meter", "kg", "mg",
    "gram", "kilogram", "milligram", "ml", "litre", "liter", "millilitre", "milliliter",
    "volt", "kv", "amp", "ma", "kw", "hz", "rpm", "rcf", "second", "sec", "minute", "min",
    "hour", "hr", "hrs", "day", "percent", "degree", "celsius", "fahrenheit", "lb", "lbs", "ft", "inch",
}
VALUE_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|°\s?[CcFf]\b|[a-zA-Z]+)")
DEGREE_UNITS = {"c": "celsius", "f": "fahrenheit"}


def clean_line(line):
    """Strip markdown emphasis, headings and bullets that Gemini adds."""
    line = re.sub(r"[*_`#>]", "", line).strip()
    return re.sub(r"^[-•]\s+", "", line)


def text_lines(text):
    return [line for line in (clean_line(raw) for raw in text.splitlines()) if line]


def tokens(text):
    """Content words, lower-cased, with a naive plural strip. Numbers are excluded
    (they are checked separately) and negations are checked only in has_negation()."""
    words = re.findall(r"[a-z]+", text.lower().replace("'", ""))
    return {
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in words
        if word not in STOPWORDS and word not in NEGATIONS
    }


def has_negation(text):
    return bool(NEGATIONS & set(re.findall(r"[a-z]+", text.lower().replace("'", ""))))


def plain_words(text):
    """All lower-case words (stop-words kept), with the same naive plural strip as tokens()."""
    return {
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in re.findall(r"[a-z]+", text.lower().replace("'", ""))
    }


def antonym_flips(source, draft):
    """Opposite-word swaps: the source uses one word of a pair and the draft uses only the other."""
    before, after = plain_words(source), plain_words(draft)
    flips = []
    for pair in ANTONYMS:
        for old, new in (pair, pair[::-1]):
            if old in before and new not in before and new in after and old not in after:
                flips.append((old, new))
    return flips


def value_units(text):
    """(number, unit) pairs for recognised units, e.g. '3000 rpm' -> ('3000', 'rpm')."""
    pairs = set()
    for number, unit in VALUE_UNIT.findall(text):
        if unit.startswith("°"):
            unit = DEGREE_UNITS[unit[-1].lower()]
        unit = "percent" if unit == "%" else unit.lower()
        # Plural strip only for unknown words, so 'celsius' is not cut to 'celsiu'.
        if unit not in UNIT_WORDS and len(unit) > 3 and unit.endswith("s"):
            unit = unit[:-1]
        if unit in UNIT_WORDS:
            pairs.add((number, unit))
    return pairs


def containment(part, whole):
    """Share of `part` tokens that also appear in `whole`."""
    return len(part & whole) / len(part) if part else 0.0


def dice(a, b):
    return 2 * len(a & b) / (len(a) + len(b)) if a or b else 0.0


def extract_draft_section(generated_text):
    """Return only the DRAFT part of the structured model output."""
    cleaned = "\n".join(text_lines(generated_text))
    match = DRAFT_SECTION.search(cleaned)
    return (match.group(1).strip(), True) if match else (cleaned, False)


def extract_steps(text):
    steps = []
    for line in text_lines(text):
        match = STEP_LINE.match(line)
        if match:
            steps.append({"number": match.group(1) or match.group(2), "text": match.group(3).strip()})
    return steps


def extract_warnings(text):
    """Non-step lines with a hazard keyword and at least three content words
    (so bare headings such as 'SAFETY WARNINGS' are ignored)."""
    return [
        line for line in text_lines(text)
        if not STEP_LINE.match(line) and WARNING_LINE.search(line) and len(tokens(line)) >= 3
    ]


def best_match(target, candidates, score):
    best_index, best_score = None, 0.0
    for index, candidate in enumerate(candidates):
        value = score(target, candidate)
        if value > best_score:
            best_index, best_score = index, value
    return best_index, best_score


# ---------------------------------------------------------------------------
# v1.2 rules. Each returns finding dicts; evaluate_revision() adds line numbers.
# ponytail: word lists, not semantics. They catch the patterns in the EXP-001 hard cases
# and miss paraphrases of them; the advisory semantic checker is the upgrade path.
# ---------------------------------------------------------------------------

# Quantity and timing words: the source uses a strong one, the draft drops it for a weak one.
STRONG_QUANTIFIERS = {"all", "every", "each", "always", "before"}
WEAK_QUANTIFIERS = {
    "some", "most", "a", "an", "one", "single", "few", "several", "many", "sometimes",
    "occasionally", "usually", "after", "during", "while", "once",
}

# Who performs a lock, tag or verification step.
ACTORS = {
    "worker", "operator", "supervisor", "technician", "engineer", "employee", "person",
    "personnel", "you", "your", "everyone", "contractor", "electrician", "manager", "staff",
    "team", "user", "analyst", "attendant", "driver",
}
ACTOR_SCOPE = {
    "lock", "lockout", "tag", "tagout", "verify", "verification", "confirm", "isolate",
    "isolation", "permit", "sign",
}

# A prohibition: "do not / never / must not" + verb + object, optionally a condition.
PROHIBITION = re.compile(
    r"\b(?:do\s+not|don'?t|never|must\s+not|must\s+never|shall\s+not|should\s+not|cannot|not)\s+(.+)",
    re.IGNORECASE,
)
CONDITION_WORDS = {"while", "whilst", "when", "unless", "until", "without", "with", "if", "that", "during"}
CLAUSE_END_WORDS = {"for"}  # "... for any reason" adds emphasis, not a condition

# Words that only say *how* to change, so they cannot show whether the change was applied.
REQUEST_WORDS = {
    "change", "replace", "increase", "decrease", "reduce", "update", "use", "add", "remove",
    "delete", "set", "make", "modify", "switch", "instead", "new", "now", "must", "should",
    "please", "require", "required", "so",
}
REMOVAL_WORDS = {"remove", "delete", "drop", "omit", "eliminate"}


def same_word(a, b):
    """Crude stem match: bypass/bypassing, raise/raised, add/adds, operate/operating."""
    if a == b:
        return True
    shorter = min(len(a), len(b))
    prefix = len(os.path.commonprefix([a, b]))
    return shorter >= 3 and prefix >= max(3, shorter - 1) and abs(len(a) - len(b)) <= 3


def parse_prohibition(warning):
    """'Never open the lid while the rotor is spinning' ->
    ('open', {'lid'}, {'while', 'rotor', 'spinning'}). None if the line forbids nothing."""
    match = PROHIBITION.search(warning)
    if not match:
        return None
    words = re.findall(r"[a-z]+", match.group(1).lower().replace("'", ""))
    if not words:
        return None
    verb, rest = words[0], words[1:]
    action, condition = rest, []
    for index, word in enumerate(rest):
        if word in CLAUSE_END_WORDS:
            action = rest[:index]
            break
        if word in CONDITION_WORDS:
            action, condition = rest[:index], rest[index:]
            break
    return verb, tokens(" ".join(action)), tokens(" ".join(condition))


def check_warning_conflicts(source_warnings, draft_steps):
    """Every draft step (new ones included) against every source prohibition: a step that,
    without negation, does the forbidden verb to the forbidden object (under the forbidden
    condition, if the warning has one) contradicts the warning."""
    findings = []
    prohibitions = [(w, parse_prohibition(w)) for w in source_warnings]
    for step in draft_steps:
        text = step["text"]
        if has_negation(text):
            continue
        words = re.findall(r"[a-z]+", text.lower().replace("'", ""))
        step_tokens = tokens(text)
        for warning, rule in prohibitions:
            if not rule:
                continue
            verb, action, condition = rule
            if not action or not any(same_word(verb, word) for word in words):
                continue
            if containment(action, step_tokens) < PARTIAL_THRESHOLD:
                continue
            if condition and containment(condition, step_tokens) < PARTIAL_THRESHOLD:
                continue
            findings.append({
                "type": "contradicts_warning", "severity": "critical",
                "detail": "Draft step does what a source warning forbids.",
                "source": warning, "draft": text,
                "evidence": f"forbidden: '{verb} {' '.join(sorted(action))}'",
            })
    return findings


def check_quantifier(source, draft_text, change_words, already_flipped):
    """all/every/each/always/before in the source replaced by a weaker word in the draft."""
    before, after = plain_words(source), plain_words(draft_text)
    removed = sorted((STRONG_QUANTIFIERS & before) - after)
    added = sorted((WEAK_QUANTIFIERS & after) - before)
    if not removed or not added:
        return []
    if {(old, new) for old in removed for new in added} <= set(already_flipped):
        return []  # e.g. before -> after: already a conflicting_instruction (antonym rule)
    requested = bool(set(added) & change_words)
    return [{
        "type": "quantifier_weakened", "severity": "review" if requested else "critical",
        "detail": "A quantity or timing word was weakened."
                  + (" The change request mentions it; confirm." if requested else ""),
        "source": source, "draft": draft_text,
        "evidence": f"'{', '.join(removed)}' -> '{', '.join(added)}'",
    }]


def actors(text):
    found = plain_words(text) & ACTORS
    return {"you" if word == "your" else word for word in found}


def check_actor(source, draft_text, change_words):
    """A lock / tag / verify step whose performer changed (e.g. 'each worker' -> 'the supervisor')."""
    if not (plain_words(source) | plain_words(draft_text)) & ACTOR_SCOPE:
        return []
    old, new = actors(source), actors(draft_text)
    if not old or old == new:
        return []
    requested = bool((new - old) & change_words)
    return [{
        "type": "actor_changed", "severity": "review" if requested else "high",
        "detail": "The person who performs this lock, tag or verification step changed."
                  + (" The change request mentions it; confirm." if requested else ""),
        "source": source, "draft": draft_text,
        "evidence": f"{', '.join(sorted(old))} -> {', '.join(sorted(new)) or 'nobody named'}",
    }]


def check_change_applied(change_request, original_text, draft):
    """Is there any sign of the requested change in the draft? Fails when the draft equals the
    original, or when none of the request's new numbers or new terms appear in it.
    Removal requests are only checked for an unchanged draft (removed words leave no trace)."""
    if not change_request.strip():
        return []
    unchanged = [line.lower() for line in text_lines(draft)] == [line.lower() for line in text_lines(original_text)]
    new_numbers = set(NUMBER.findall(change_request)) - set(NUMBER.findall(original_text))
    new_terms = tokens(change_request) - tokens(original_text) - REQUEST_WORDS
    expected = sorted(new_numbers) + sorted(new_terms)
    if plain_words(change_request) & REMOVAL_WORDS and not new_numbers:
        expected = []
    seen = (set(NUMBER.findall(draft)) & new_numbers) | (tokens(draft) & new_terms)
    if not unchanged and (not expected or seen):
        return []
    return [{
        "type": "change_not_applied", "severity": "critical",
        "detail": "The draft is identical to the original." if unchanged
                  else "None of the change request's new values or terms appear in the draft.",
        "source": change_request,
        "evidence": f"expected one of: {', '.join(expected)}" if expected else "draft equals original",
    }]


def line_number(lines, text):
    """1-based number of the first line containing `text`, or None."""
    if text:
        for number, line in enumerate(lines, start=1):
            if text in line:
                return number
    return None


def evaluate_revision(original_text, generated_text, change_request=""):
    """
    Automated checks of a generated draft against the original SOP.
    Returns status 'fail', 'needs_review' or 'pass_automated'. None of these
    is a safety approval; only a qualified human reviewer can approve.
    """
    draft, draft_found = extract_draft_section(generated_text)
    change_tokens = tokens(change_request)
    allowed_numbers = set(NUMBER.findall(original_text)) | set(NUMBER.findall(change_request))

    source_line_tokens = [tokens(line) for line in text_lines(original_text)]
    source_warnings = extract_warnings(original_text)
    source_steps = extract_steps(original_text)
    draft_lines = text_lines(draft)
    draft_line_tokens = [tokens(line) for line in draft_lines]
    draft_steps = extract_steps(draft)
    draft_step_tokens = [tokens(step["text"]) for step in draft_steps]

    findings = []
    original_lines = text_lines(original_text)

    def add(kind, severity, detail, **extra):
        findings.append({"type": kind, "severity": severity, "detail": detail, **extra})

    def add_located(finding):
        """v1.2 findings carry the line numbers of their quoted evidence."""
        finding["source_line"] = line_number(original_lines, finding.get("source"))
        finding["draft_line"] = line_number(draft_lines, finding.get("draft"))
        findings.append(finding)

    change_words = plain_words(change_request)

    def check_conflict(source, draft_text, label):
        if has_negation(source) != has_negation(draft_text):
            add("conflicting_instruction", "critical", f"{label} polarity changed (negation added or removed).",
                source=source, draft=draft_text)
        flips = antonym_flips(source, draft_text)
        for old, new in flips:
            requested = new in change_words
            add("conflicting_instruction", "review" if requested else "critical",
                f"{label} says '{new}' where the source says '{old}'."
                + (" The change request mentions it; confirm." if requested else ""),
                source=source, draft=draft_text)
        for finding in check_quantifier(source, draft_text, change_words, flips) + check_actor(source, draft_text, change_words):
            add_located(finding)

    if not draft_found:
        add("draft_section_not_found", "review",
            "No 'DRAFT:' section found; the whole response was evaluated.")
    if not source_steps:
        add("no_source_steps_detected", "review",
            "No numbered steps found in the source, so step checks could not run.")
    if not source_warnings:
        add("no_source_warnings_detected", "review",
            "No warning lines found in the source, so warning recall could not be measured.")

    # 1. Warning preservation
    preserved = altered = 0
    for warning in source_warnings:
        index, score = best_match(tokens(warning), draft_line_tokens, containment)
        matched_line = draft_lines[index] if index is not None else None
        if score >= MATCH_THRESHOLD:
            preserved += 1
        elif score >= PARTIAL_THRESHOLD:
            altered += 1
            add("altered_warning", "review", "Warning wording changed; confirm the meaning is unchanged.",
                source=warning, draft=matched_line, score=round(score, 2))
        else:
            add("missing_warning", "critical", "Source warning not found in the draft.",
                source=warning, score=round(score, 2))
        if score >= PARTIAL_THRESHOLD:
            check_conflict(warning, matched_line, "Warning")

    # 2. Step mapping: omitted, altered, conflicting
    positions = []  # (source step, draft index) for each source step found, in source order
    matched_steps = altered_steps = 0
    for step in source_steps:
        step_tokens = tokens(step["text"])
        index, score = best_match(step_tokens, draft_step_tokens, dice)
        if score < PARTIAL_THRESHOLD:
            if containment(step_tokens, change_tokens) >= PARTIAL_THRESHOLD:
                add("omitted_step", "review", "Step removed; the change request appears to ask for this. Confirm.",
                    source=step["text"])
            else:
                add("omitted_step", "critical", "Source step not found in the draft.", source=step["text"])
            continue

        draft_step = draft_steps[index]
        positions.append((step, index))
        if score >= MATCH_THRESHOLD:
            matched_steps += 1
        else:
            altered_steps += 1
            new_words = draft_step_tokens[index] - step_tokens
            if containment(new_words, change_tokens) >= MATCH_THRESHOLD:
                add("altered_step", "info", "Step changed as described in the change request.",
                    source=step["text"], draft=draft_step["text"])
            else:
                add("altered_step", "review", "Step wording changed beyond the change request.",
                    source=step["text"], draft=draft_step["text"], score=round(score, 2))
        check_conflict(step["text"], draft_step["text"], "Step")

    # 3. Step-order integrity: share of source step pairs kept in the same order
    pairs = concordant = 0
    inversions = []
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pairs += 1
            # Equal positions mean two source steps were merged into one draft step: not a reversal.
            if positions[i][1] <= positions[j][1]:
                concordant += 1
            else:
                inversions.append({"before": positions[i][0]["text"], "after": positions[j][0]["text"]})
    if inversions:
        add("step_order_violation", "critical",
            "Source steps appear in a different order in the draft.", pairs=inversions)

    # 4. Duplicated steps
    duplicates = 0
    for i in range(len(draft_steps)):
        for j in range(i + 1, len(draft_steps)):
            if dice(draft_step_tokens[i], draft_step_tokens[j]) >= DUPLICATE_THRESHOLD:
                duplicates += 1
                add("duplicated_step", "review", "Two draft steps are near-identical.",
                    draft=draft_steps[j]["text"])

    # 5. Unsupported instructions and values
    unsupported = 0
    for step, step_tokens in zip(draft_steps, draft_step_tokens):
        support = max(
            (containment(step_tokens, line_tokens | change_tokens) for line_tokens in source_line_tokens),
            default=containment(step_tokens, change_tokens),
        )
        if support < PARTIAL_THRESHOLD:
            unsupported += 1
            add("unsupported_instruction", "critical",
                "Draft step is not supported by the source or the change request.",
                draft=step["text"], support=round(support, 2))

    value_lines = [step["text"] for step in draft_steps] + extract_warnings(draft)
    new_values = sorted({n for line in value_lines for n in NUMBER.findall(line)} - allowed_numbers)
    if new_values:
        add("unsupported_value", "critical",
            "Numeric values not present in the source or the change request.", values=new_values)

    known_units = {}
    for number, unit in value_units(original_text) | value_units(change_request):
        known_units.setdefault(number, set()).add(unit)
    unit_changes = sorted({
        f"{number} {unit}"
        for line in value_lines for number, unit in value_units(line)
        if known_units.get(number) and unit not in known_units[number]
    })
    if unit_changes:
        add("unsupported_value", "critical",
            "Same number as the source but a different unit.", values=unit_changes)

    # 6. v1.2: new steps that do what a warning forbids, and change requests that were ignored
    for finding in check_warning_conflicts(source_warnings, draft_steps) + check_change_applied(change_request, original_text, draft):
        add_located(finding)

    def ratio(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    metrics = {
        "source_warnings": len(source_warnings),
        "warning_recall": ratio(preserved, len(source_warnings)),
        "warning_recall_lenient": ratio(preserved + altered, len(source_warnings)),
        "source_steps": len(source_steps),
        "draft_steps": len(draft_steps),
        "step_coverage": ratio(matched_steps + altered_steps, len(source_steps)),
        "order_integrity": ratio(concordant, pairs),
        "unsupported_instruction_rate": ratio(unsupported, len(draft_steps)),
        "unsupported_values": len(new_values) + len(unit_changes),
        "omitted_steps": sum(f["type"] == "omitted_step" for f in findings),
        "altered_steps": altered_steps,
        "duplicated_steps": duplicates,
        "conflicting_instructions": sum(f["type"] == "conflicting_instruction" for f in findings),
        "contradicted_warnings": sum(f["type"] == "contradicts_warning" for f in findings),
        "weakened_quantifiers": sum(f["type"] == "quantifier_weakened" for f in findings),
        "actor_changes": sum(f["type"] == "actor_changed" for f in findings),
        "change_applied": not any(f["type"] == "change_not_applied" for f in findings) if change_request.strip() else None,
    }

    severities = {f["severity"] for f in findings}
    status = ("fail" if severities & FAILING_SEVERITIES
              else "needs_review" if "review" in severities else "pass_automated")
    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])

    return {
        "status": status,
        "evaluator_version": EVALUATOR_VERSION,
        "metrics": metrics,
        "findings": findings,
        "disclaimer": (
            "Automated text checks only. 'pass_automated' means no rule fired; it is not "
            "safety approval. A qualified human reviewer must approve before use."
        ),
    }
