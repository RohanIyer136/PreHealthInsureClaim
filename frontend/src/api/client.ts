import type { CaseDetail, CaseSummary, DecisionWorkspace } from "../types/api";

const base = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export function isDemoMode(): boolean {
  return import.meta.env.VITE_WORKSPACE_MODE === "demo";
}

function casesPath(): string {
  return isDemoMode() ? "/api/v1/demo/cases" : "/api/v1/cases";
}

export class ApiError extends Error {
  constructor(public status: number) {
    const messages: Record<number, string> = {
      404: "This case is no longer available. Refresh the case queue.",
      422: "The case inputs could not be validated. Review the submitted information.",
      500: "The workspace service encountered an internal error. Please try again.",
      502: "AI output did not pass validation. No new workspace was produced. Please retry.",
      503: "Local AI inference is unavailable or failed. No authorization decision was made. Please retry when the service is available.",
    };
    super(
      messages[status] ||
        "The request could not be completed. Please try again.",
    );
  }
}

async function request<T>(
  path: string,
  signal?: AbortSignal,
  method = "GET",
): Promise<T> {
  const response = await fetch(base + path, {
    method,
    signal,
    credentials: "omit",
  });
  if (!response.ok) throw new ApiError(response.status);
  return response.json() as Promise<T>;
}

export const api = {
  listCases: (signal?: AbortSignal) =>
    request<CaseSummary[]>(casesPath(), signal),
  getCase: (id: string, signal?: AbortSignal) =>
    request<CaseDetail>(`${casesPath()}/${encodeURIComponent(id)}`, signal),
  analyzeCase: (id: string, signal?: AbortSignal) =>
    request<DecisionWorkspace>(
      `${casesPath()}/${encodeURIComponent(id)}/analyze`,
      signal,
      "POST",
    ),
};

export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Cannot reach the workspace service. Check the local API connection and retry.";
}
