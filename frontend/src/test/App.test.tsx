import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import App from "../App";
import { api, ApiError } from "../api/client";
import { WorkspaceResult } from "../components/WorkspaceResult";
import { StatusBadge } from "../components/StatusBadge";
import type { ReadinessStatus } from "../types/api";
import { cases, detail, secondDetail, workspace } from "./fixtures";

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mockHttp(
  analyze: () => Promise<Response> = async () => response(workspace),
) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (init?.method === "POST") return analyze();
      if (path.endsWith("/cases")) return response(cases);
      if (path.endsWith("/CASE-101")) return response(detail);
      if (path.endsWith("/CASE-102")) return response(secondDetail);
      throw new Error("Unexpected test request");
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
async function loadApp() {
  render(<App />);
  await screen.findByRole("button", { name: /Analyze Authorization/ });
}

describe("case review", () => {
  it("renders API queue, selects cases, and exposes only submitted documents", async () => {
    const fetchMock = mockHttp();
    await loadApp();
    const queue = screen.getByRole("complementary", { name: "Case queue" });
    expect(
      within(queue).getAllByRole("button", { name: /CASE-10/ }),
    ).toHaveLength(2);
    fireEvent.click(within(queue).getByRole("button", { name: /CASE-102/ }));
    await waitFor(() =>
      expect(screen.getByRole("main")).toHaveTextContent(
        "Authorization / CASE-102",
      ),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/cases/CASE-102"),
      expect.objectContaining({ method: "GET" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Clinical Note.*NOTE-101/ }),
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(detail.documents[0].content);
    fireEvent.click(screen.getByRole("button", { name: "Close source" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("submits once, shows honest pending state, then renders validated workspace and provenance", async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetchMock = mockHttp(() => pending);
    await loadApp();
    fireEvent.click(
      screen.getByRole("button", { name: /Analyze Authorization/ }),
    );
    expect(
      screen.getByText("Preparing decision workspace..."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Preparing workspace/ }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /CASE-102/ })).toBeDisabled();
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/CASE-101/analyze"),
      expect.objectContaining({ method: "POST", credentials: "omit" }),
    );
    await act(async () => finish(response(workspace)));
    expect(await screen.findByText("Evidence Required")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Decision workspace" }), {
      key: "ArrowLeft",
    });
    expect(screen.getByRole("tab", { name: "Case & documents" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Case & documents" }), {
      key: "ArrowRight",
    });
    expect(
      screen.getByRole("tab", { name: "Decision workspace" }),
    ).toHaveFocus();
    expect(
      screen.queryByText("Preparing decision workspace..."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Physiotherapy report required."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Treatment dates require reconciliation."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Treatment frequency not stated."),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /View source: NOTE-101/ }),
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector("mark")).toHaveTextContent(
      "Six weeks of physiotherapy completed.",
    );
    expect(dialog).toHaveTextContent("Further assessment requested.");
    expect(document.body).not.toHaveTextContent(
      /\b(APPROVED|REJECTED|Denied|Authorized)\b/,
    );
  });

  it.each([422, 500, 502, 503])(
    "renders useful HTTP %s failures without a fabricated result",
    async (status) => {
      mockHttp(async () =>
        response({ error: { message: "PRIVATE internal body" } }, status),
      );
      await loadApp();
      fireEvent.click(
        screen.getByRole("button", { name: /Analyze Authorization/ }),
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        new ApiError(status).message,
      );
      expect(screen.queryByText("Workspace readiness")).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Analyze Authorization/ }),
      ).toBeEnabled();
      expect(document.body).not.toHaveTextContent(
        /PRIVATE|\b(APPROVED|REJECTED|Denied)\b/,
      );
      if (status === 503)
        expect(screen.getByRole("alert")).toHaveTextContent(
          "No authorization decision was made",
        );
    },
  );

  it("handles queue errors and retries without a running API", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValue(response(cases));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach");
    fetchMock.mockImplementation(async (input: RequestInfo | URL) =>
      response(String(input).endsWith("/cases") ? cases : detail),
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("button", { name: /Analyze Authorization/ }),
    ).toBeInTheDocument();
  });

  it("handles empty queue and search results", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response([])),
    );
    render(<App />);
    expect(
      await screen.findByText("No authorization cases available."),
    ).toBeInTheDocument();
  });

  it("handles detail errors with retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        response(
          String(input).endsWith("/cases") ? cases : {},
          String(input).endsWith("/cases") ? 200 : 404,
        ),
      ),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This case is no longer available",
    );
    expect(
      screen.queryByRole("button", { name: /Analyze Authorization/ }),
    ).not.toBeInTheDocument();
  });

  it("ignores stale case detail when selection changes", async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/cases")) return response(cases);
        return path.endsWith("CASE-101") ? pending : response(secondDetail);
      }),
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /CASE-102/ }));
    await waitFor(() =>
      expect(screen.getByRole("main")).toHaveTextContent(
        "Authorization / CASE-102",
      ),
    );
    await act(async () => finish(response(detail)));
    expect(screen.getByRole("main")).not.toHaveTextContent(
      "Authorization / CASE-101",
    );
  });
});

describe("workspace semantics", () => {
  it.each<[ReadinessStatus, string]>([
    ["READY_FOR_EXPERT_REVIEW", "Ready for Expert Review"],
    ["EVIDENCE_REQUIRED", "Evidence Required"],
    ["HUMAN_REVIEW_REQUIRED", "Human Review Required"],
    ["PROCESSING", "Processing"],
  ])("renders %s as readiness, not a decision", (status, text) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("renders status, empty findings, and real audit events without invented stages", () => {
    render(
      <WorkspaceResult
        workspace={{
          ...workspace,
          missing_evidence: [],
          conflicts: [],
          clinical_results: [
            {
              ...workspace.clinical_results[0],
              status: "REQUIRES_HUMAN_REVIEW",
            },
          ],
          insurance_results: [
            { ...workspace.insurance_results[0], status: "NOT_SATISFIED" },
          ],
        }}
        openSource={vi.fn()}
      />,
    );
    expect(screen.getByText("Requires human review")).toBeInTheDocument();
    expect(screen.getByText("Not satisfied")).toBeInTheDocument();
    expect(
      screen.getByText("No missing information identified."),
    ).toBeInTheDocument();
    expect(screen.getByText("No conflicts identified.")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Decision Trace"));
    const auditSummary = screen.getByText("Synthetic test event.", { selector: "p" });
    expect(auditSummary).toBeVisible();
    fireEvent.click(within(auditSummary.closest("li")!).getByText("Technical details"));
    expect(screen.getByText(/workspace-service/)).toBeVisible();
  });

  it("API client encodes case IDs and requires no answer-key fields", async () => {
    const fetchMock = vi.fn(async () => response(detail));
    vi.stubGlobal("fetch", fetchMock);
    await api.getCase("CASE/unsafe");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("CASE%2Funsafe"),
      expect.any(Object),
    );
    expect(Object.keys(workspace)).not.toContain("expectations");
  });

  it("production frontend reads API payloads only, never benchmark answers", () => {
    function inspect(directory: string) {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = resolve(directory, entry.name);
        if (entry.isDirectory() && entry.name !== "test") inspect(path);
        else if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) {
          expect(readFileSync(path, "utf8")).not.toMatch(
            /golden|benchmark|expectations|expected_readiness|evaluation\//i,
          );
        }
      }
    }
    inspect(resolve("src"));
  });
});

describe("pre-evaluated demo mode", () => {
  it.each<[ReadinessStatus, string]>([
    ["READY_FOR_EXPERT_REVIEW", "Ready for Expert Review"],
    ["EVIDENCE_REQUIRED", "Evidence Required"],
    ["HUMAN_REVIEW_REQUIRED", "Human Review Required"],
  ])("discloses demo serving and preserves %s and source inspection", async (status, text) => {
    vi.stubEnv("VITE_WORKSPACE_MODE", "demo");
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    const fetchMock = mockHttp(() => pending);
    await loadApp();
    expect(screen.getByText("Demo Mode - pre-evaluated synthetic authorization cases")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Analyze Authorization/ }));
    expect(screen.getByText("Loading a pre-evaluated workspace. No live inference is running.")).toBeVisible();
    expect(screen.queryByText(/Local inference is running/)).not.toBeInTheDocument();
    await act(async () => finish(response({ ...workspace, readiness_status: status })));
    expect(await screen.findByText(text)).toBeVisible();
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes("/api/v1/demo/cases"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /View source: NOTE-101/ }));
    expect(screen.getByRole("dialog").querySelector("mark")).toHaveTextContent("Six weeks of physiotherapy completed.");
    expect(document.body).not.toHaveTextContent(/\b(APPROVED|REJECTED|Denied|Authorized)\b/);
  });
});
