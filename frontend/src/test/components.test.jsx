import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import EvaluationReport from "../components/EvaluationReport.jsx";
import SignOffDialog from "../components/SignOffDialog.jsx";

vi.mock("../api.js", () => ({
  getVersionDiff: vi.fn(async () => ({
    blocks: [
      { tag: "equal", original: ["Title"], draft: ["Title"], original_start: 1, draft_start: 1 },
      { tag: "replace", original: ["Switch off the isolator."], draft: ["Switch on the isolator."], original_start: 2, draft_start: 2 },
    ],
    source_warnings: [],
    similarity: 0.8,
  })),
}));

const METRICS = { warning_recall: 1, source_warnings: 1, unsupported_instruction_rate: 0, unsupported_values: 0,
  order_integrity: 1, omitted_steps: 0, duplicated_steps: 0, conflicting_instructions: 1 };

describe("EvaluationReport", () => {
  it("says 'No automated rule fired' and never 'safe' when there are no findings", () => {
    render(<EvaluationReport evaluation={{ status: "pass_automated", metrics: METRICS, findings: [], evaluator_version: "v" }} />);
    expect(screen.getByText(/No automated rule fired/)).toBeTruthy();
    expect(screen.getByText("No rule fired")).toBeTruthy();
    expect(screen.queryByText(/\bsafe\b/i)).toBeNull();
  });

  it("offers 'Show in comparison' for a finding with a line number", () => {
    const finding = { type: "conflicting_instruction", severity: "critical", detail: "Polarity changed.",
      source: "Switch off the isolator.", source_line: 2, source_page: 1, draft: "Switch on the isolator.", draft_line: 2 };
    const onShow = vi.fn();
    render(<EvaluationReport evaluation={{ status: "fail", metrics: METRICS, findings: [finding], evaluator_version: "v" }} onShowInComparison={onShow} />);
    expect(screen.getByText(/line 2, PDF page 1/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Show in comparison/ }));
    expect(onShow).toHaveBeenCalledWith(finding);
  });
});

describe("DiffView", () => {
  it("marks changes with text, not colour only, and highlights the referenced line", async () => {
    const { default: DiffView } = await import("../components/DiffView.jsx");
    render(<DiffView versionId="v1" highlight={{ side: "draft", line: 2 }} />);
    await waitFor(() => expect(document.getElementById("diff-draft-2")).toBeTruthy());
    expect(screen.getByText("Removed:")).toBeTruthy();
    expect(screen.getByText("Added:")).toBeTruthy();
    const highlighted = document.getElementById("diff-draft-2");
    expect(highlighted.className).toContain("diff-highlight");
    expect(document.activeElement).toBe(highlighted);
  });
});

describe("SignOffDialog", () => {
  const version = { version_number: 3, filename: "pump.pdf", evaluation_status: "fail" };

  it("requires a justification when the automated checks did not pass", async () => {
    const onSign = vi.fn();
    render(<SignOffDialog open version={version} initialJustification="" onSign={onSign} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Your password"), { target: { value: "secret-password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign and approve" }).closest("form"));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Explain why"));
    expect(onSign).not.toHaveBeenCalled();
  });

  it("passes justification and password, and shows a server refusal in the dialog", async () => {
    const onSign = vi.fn().mockRejectedValue(new Error("Re-enter your password to sign this approval."));
    render(<SignOffDialog open version={version} initialJustification="Checked by hand." onSign={onSign} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Your password"), { target: { value: "wrong" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign and approve" }).closest("form"));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Re-enter your password to sign this approval.");
    expect(onSign).toHaveBeenCalledWith({ justification: "Checked by hand.", password: "wrong" });
  });
});
