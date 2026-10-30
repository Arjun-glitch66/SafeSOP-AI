import { Badge } from "../components/ui.jsx";
import { useBackend, useTitle } from "../state.jsx";

const FRAMEWORK = [
  ["Warning preservation", "Each source warning must appear in the draft (token containment ≥ 0.8). 0.5–0.8 is flagged as altered for review.", "Critical"],
  ["Unsupported instructions and values", "Draft steps must be supported by the source or the change request. New numbers, and known numbers with a different unit, are flagged.", "Critical"],
  ["Step-order integrity", "Share of source step pairs that keep their relative order in the draft.", "Critical"],
  ["Omitted, altered, duplicated and conflicting steps", "Source steps are matched to draft steps. Removed steps, wording changes, near-duplicates, negation flips and opposite words (on/off, open/close) are reported.", "High"],
  ["Contradicted warnings", "Every draft step, including new ones, is compared with every source prohibition ('do not / never' + action). A step that performs the forbidden action fails.", "Critical"],
  ["Weakened quantifiers and timing", "'all / every / each / always / before' replaced by 'some / most / a / after …' in a matched warning or step.", "Critical"],
  ["Changed actor", "The person who applies a lock or tag, or verifies, changed (e.g. 'each worker' -> 'the supervisor').", "High"],
  ["Change not applied", "The draft equals the original, or none of the change request's new values or terms appear in it.", "Critical"],
  ["Required elements for the SOP type", "With an SOP type chosen at upload (e.g. lockout/tagout), each required element present in the original must still be in the draft.", "Critical"],
  ["Hierarchy-of-controls downgrade", "An engineering or elimination control (guard, interlock, ventilation, isolation) replaced by training, signs or PPE.", "High"],
  ["Structured matching (prompt v3)", "Drafts that cite source ids (S1.., W1..) are matched by id, not by text. A warning declared removed is still critical; a step labelled unchanged is still compared with its source.", "Critical"],
  ["Uncertain cases", "Borderline matches, missing sections or undetectable structure give 'needs review', never a pass.", "Review"],
];

export default function ChecksPage() {
  useTitle("Automated checks");
  const { evaluatorVersion } = useBackend();
  return (
    <>
      <div className="page-intro"><div><h1>Automated checks</h1><p>The checks compare each draft with the original PDF. They flag problems for a reviewer; they never approve a draft. A draft with no findings shows "No rule fired", not "safe".</p></div><Badge tone="blue">{evaluatorVersion || "evaluator"}</Badge></div>
      <section className="panel" aria-labelledby="framework-heading">
        <div className="panel-heading"><div><h2 id="framework-heading">Evaluation framework</h2><p>Full definitions: research_logbook/EVALUATION_FRAMEWORK.md</p></div></div>
        {FRAMEWORK.map(([title, text, level]) => (
          <div className="framework-row" key={title}><div className="row-main"><strong>{title}</strong><span>{text}</span></div><Badge tone={level === "Review" ? "amber" : "red"}>{level}</Badge></div>
        ))}
        <div className="panel-footnote">The checks compare words, not meaning: correct paraphrases may be flagged for review, and meaning changes outside the built-in word lists are not detected. Automated checks never replace qualified human approval.</div>
      </section>
    </>
  );
}
