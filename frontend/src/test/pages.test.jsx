import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import ChangeLog, { changeRows } from "../components/ChangeLog.jsx";

const auth = { user: { id: "u-admin", username: "admin", role: "admin" }, can: () => true };
const notice = { show: vi.fn() };
vi.mock("../state.jsx", async () => {
  const { useEffect, useState } = await import("react");
  return {
    useAuth: () => auth,
    useNotice: () => notice,
    useBackend: () => ({ online: true }),
    useTitle: () => {},
    // Same contract as the real hook, without the stale-response guard.
    useResource: (load, deps) => {
      const [state, setState] = useState({ data: null, error: null, loading: true });
      const [tick, setTick] = useState(0);
      useEffect(() => { load().then((data) => setState({ data, error: null, loading: false }), (error) => setState({ data: null, error, loading: false })); }, [...deps, tick]);  // eslint-disable-line react-hooks/exhaustive-deps
      return { ...state, reload: () => setTick((t) => t + 1) };
    },
  };
});

const api = vi.hoisted(() => ({
  getOverview: vi.fn(),
  getUsers: vi.fn(),
  updateUser: vi.fn(),
  createUser: vi.fn(),
  getAuditEvents: vi.fn(),
  verifyAuditChain: vi.fn(),
}));
vi.mock("../api.js", () => api);

beforeEach(() => { notice.show.mockReset(); });

describe("ChangeLog", () => {
  const structured = {
    steps: [
      { id: "R1", text: "Close the valve.", source_step_ids: ["S1"], change_type: "unchanged", reason: "" },
      { id: "R2", text: "Flush with 10 litres.", source_step_ids: ["S2"], change_type: "modified", reason: "The request doubles the flush volume." },
      { id: "R3", text: "Log the flush.", source_step_ids: [], change_type: "added", reason: "" },
    ],
    warnings: [{ id: "RW1", text: "WARNING: Never open the casing.", source_warning_id: "W1", reason: "" }],
    removed_warning_ids: ["W2"],
  };

  it("lists only changed items, with reasons, and flags a missing reason", () => {
    expect(changeRows(structured).map((row) => `${row.id}:${row.kind}`)).toEqual(["R2:modified", "R3:added", "W2:removed"]);
    render(<ChangeLog structuredJson={JSON.stringify(structured)} />);
    expect(screen.getByText("The request doubles the flush volume.")).toBeTruthy();
    expect(screen.getByText("No reason given")).toBeTruthy();
    expect(screen.queryByText("Close the valve.")).toBeNull();
    // Long reasons must wrap, not hide behind a horizontal scroll (found in the browser test).
    expect(screen.getByRole("table").className).toContain("text-table");
    expect(screen.getByText("The request doubles the flush volume.").className).toContain("wrap");
  });

  it("says when a version predates structured output or reasons, instead of inventing them", () => {
    const { unmount } = render(<ChangeLog structuredJson={null} />);
    expect(screen.getByText(/before structured output/)).toBeTruthy();
    unmount();
    const v4 = { ...structured, steps: structured.steps.map(({ reason: _reason, ...step }) => step), warnings: [] };
    render(<ChangeLog structuredJson={JSON.stringify(v4)} />);
    expect(screen.getByText(/before prompt v5/)).toBeTruthy();
    expect(screen.queryByText("No reason given")).toBeNull();
  });
});

describe("DashboardPage", () => {
  it("shows live counts and the review queue from /api/overview", async () => {
    api.getOverview.mockResolvedValue({
      documents: 3, versions: 5, running_jobs: 0,
      versions_by_status: { draft: 2, needs_revision: 1, approved: 2 },
      versions_by_evaluation: { fail: 1, needs_review: 2, pass_automated: 2 },
      awaiting_review: [{ id: "v9", version_number: 4, status: "draft", created_at: "2026-11-06T10:00:00Z", created_by: "alice",
        document_id: "d1", filename: "pump.pdf", evaluation_status: "fail" }],
      recent_decisions: [],
    });
    const { default: DashboardPage } = await import("../pages/DashboardPage.jsx");
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText("Version 4")).toBeTruthy();
    expect(screen.getByText("Awaiting review").parentElement.parentElement.textContent).toContain("3");
    expect(screen.getByRole("link", { name: "Review" }).getAttribute("href")).toBe("/versions/v9/review");
    expect(screen.getByText("No review decisions yet.")).toBeTruthy();
  });
});

describe("UsersPage", () => {
  it("changes a role through the API and reports a refusal", async () => {
    api.getUsers.mockResolvedValue([
      { id: "u-admin", username: "admin", role: "admin", created_at: "2026-11-01T00:00:00Z" },
      { id: "u-rob", username: "rob", role: "reviewer", created_at: "2026-11-01T00:00:00Z" },
    ]);
    api.updateUser.mockRejectedValueOnce(new Error("This is the only admin. Make another user admin first."));
    const { default: UsersPage } = await import("../pages/UsersPage.jsx");
    render(<MemoryRouter><UsersPage /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("Role of admin"), { target: { value: "reviewer" } });
    await waitFor(() => expect(notice.show).toHaveBeenCalledWith(expect.stringContaining("only admin"), "error"));
    expect(api.updateUser).toHaveBeenCalledWith("u-admin", { role: "reviewer" });
  });

  it("refuses a short password before calling the API", async () => {
    api.getUsers.mockResolvedValue([]);
    const { default: UsersPage } = await import("../pages/UsersPage.jsx");
    render(<MemoryRouter><UsersPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "newbie" } });
    fireEvent.change(screen.getByLabelText(/Initial password/), { target: { value: "short" } });
    fireEvent.submit(screen.getByRole("button", { name: /Create user/ }).closest("form"));
    expect(notice.show).toHaveBeenCalledWith(expect.stringContaining("at least 10"), "error");
    expect(api.createUser).not.toHaveBeenCalled();
  });
});

describe("AuditPage", () => {
  it("shows a broken chain as an alert", async () => {
    api.getAuditEvents.mockResolvedValue({ events: [], total: 0 });
    api.verifyAuditChain.mockResolvedValue({ ok: false, events: 4, broken_at: 3, event_id: "e3", reason: "hash does not match" });
    const { default: AuditPage } = await import("../pages/AuditPage.jsx");
    render(<MemoryRouter><AuditPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /Verify chain/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("Chain broken at event #3");
  });
});
