import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DecisionWorkspace } from "../types/api";
import { WorkspaceResult } from "../components/WorkspaceResult";
import { evaluationSummary, tracePresentation } from "../utils/workspacePresentation";
import { workspace } from "./fixtures";

const clinicalSteps = ["POLICY_ELIGIBILITY", "DOCUMENT_COMPLETENESS", "CLINICAL_RETRIEVAL", "EVIDENCE_EXTRACTION", "CLINICAL_REASONING"];
const unsupported = "Clinical knowledge/capability for the requested service is unavailable; expert review is required.";
const administrative = "Explicit service configuration requires deterministic checks only.";
const terminal = "Configured terminal deterministic finding; clinical preparation deferred.";
function event(action: string, details: string | null = null) {
  return { event_id: action, action, details, actor: "decision-workspace-service", timestamp: "2026-10-04T12:00:00Z" };
}
function example(count: number, missing = "", reason = ""): DecisionWorkspace {
  const plan = { steps: count ? clinicalSteps : ["POLICY_ELIGIBILITY", "DOCUMENT_COMPLETENESS", "HUMAN_REVIEW"],
    deferred: reason === unsupported || reason === terminal ? clinicalSteps.slice(2) : [],
    reasons: [reason || "Explicit service configuration requires clinical evaluation."], requires_escalation: !!reason };
  return { ...workspace, readiness_status: reason ? "HUMAN_REVIEW_REQUIRED" : missing ? "EVIDENCE_REQUIRED" : "READY_FOR_EXPERT_REVIEW",
    missing_evidence: missing ? [`required_document_roles_present: Missing required document roles: ${missing}`] : [],
    conflicts: reason ? [reason] : [],
    insurance_results: [{ ...workspace.insurance_results[0], criterion_id: "required_document_roles_present",
      status: missing ? "INSUFFICIENT_EVIDENCE" : "SATISFIED", explanation: missing ? `Missing required document roles: ${missing}` : "Required roles are present." }],
    clinical_results: Array.from({ length: count }, (_, i) => ({ ...workspace.clinical_results[0], criterion_id: `criterion-${i}` })),
    audit_trail: [event("DETERMINISTIC_RULES_COMPLETED", "Checks completed."), event("EXECUTION_PLANNED", JSON.stringify(plan)),
      ...[count ? "EVIDENCE_EXTRACTION_COMPLETED" : "EVIDENCE_EXTRACTION_SKIPPED",
        count ? "CLINICAL_KNOWLEDGE_RETRIEVED" : "CLINICAL_RETRIEVAL_SKIPPED",
        count ? "CLINICAL_REASONING_COMPLETED" : "ADMINISTRATIVE_PREPARATION_ONLY"].map(action => event(action))] };
}
describe("evaluation presentation", () => {
  it.each([
    ["ORTH-01", 5, "", "", "Required documents present", "Completed with AI - 5 criteria evaluated", "Ready for Expert Review"],
    ["ORTH-02", 5, "physiotherapy", "", "Physiotherapy report missing", "Completed with AI - 5 criteria evaluated", "Evidence Required"],
    ["SURG-02", 2, "", "", "Required documents present", "Completed with AI - 2 criteria evaluated", "Ready for Expert Review"],
    ["SURG-03", 2, "diagnostic_imaging", "", "Diagnostic imaging report missing", "Completed with AI - 2 criteria evaluated", "Evidence Required"],
    ["ONC-03", 0, "", unsupported, "Required documents present", "Not supported - Expert review required", "Human Review Required"],
    ["ACUTE-04", 0, "", administrative, "Required documents present", "Not required - Administrative pathway", "Human Review Required"],
  ] as const)("renders %s without deriving from its identity", (id, count, missing, reason, documents, clinical, readiness) => {
    const source = { ...example(count, missing, reason), authorization_id: `PA-MD-${id}` };
    render(<WorkspaceResult workspace={source} openSource={vi.fn()} />);
    const summary = screen.getByRole("region", { name: "How this case was evaluated" });
    expect(summary).toHaveTextContent(documents);
    expect(summary).toHaveTextContent(clinical);
    expect(summary).toHaveTextContent("Deterministic checksCompleted");
    expect(summary).toHaveTextContent("Final authorizationHuman reviewer");
    expect(summary).toHaveTextContent(missing ? "Missing information identified" : "No gaps recorded within evaluated scope");
    expect(screen.getByText(readiness)).toBeVisible();
    expect(screen.getByText(/Final authorization decision remains with the human reviewer/)).toBeVisible();
    expect(document.body).not.toHaveTextContent(/\b(Approved|Rejected|Eligible)\b/);
    expect(evaluationSummary({ ...source, authorization_id: "UNRELATED" }, false)).toEqual(evaluationSummary(source, false));
  });
  it("recognizes terminal routing without implying a clinical decision", () => {
    expect(evaluationSummary(example(0, "", terminal), false)).toContainEqual(["Clinical evaluation", "Skipped - Policy/coverage finding"]);
  });
  it("recognizes unavailable knowledge after retrieval preflight without claiming clinical execution", () => {
    const source = example(0);
    source.audit_trail[1].details = JSON.stringify({ steps: clinicalSteps.slice(0, 3), deferred: clinicalSteps.slice(3),
      reasons: ["Explicit service configuration requires clinical evaluation.",
        "Clinical retrieval did not resolve exactly one artifact; expert review is required."], requires_escalation: true });
    source.audit_trail[3] = event("CLINICAL_KNOWLEDGE_RETRIEVED");
    expect(evaluationSummary(source, false)).toContainEqual(["Clinical evaluation", "Not supported - Expert review required"]);
    expect(tracePresentation(source.audit_trail[1]).summary).toBe("Clinical guidance did not resolve uniquely; expert review is required.");
  });
  it.each(["missing", "malformed", "invalid fields", "unknown reason", "contradictory completion", "contradictory plan", "completed but unsupported", "duplicate plan", "duplicate completion", "conflicting reasons", "administrative event alone"])("fails conservatively for %s", change => {
    const source = example(0, "", unsupported);
    if (change === "missing") source.audit_trail = source.audit_trail.filter(e => e.action !== "EXECUTION_PLANNED");
    if (change === "malformed") source.audit_trail[1].details = "{broken";
    if (change === "invalid fields") source.audit_trail[1].details = JSON.stringify({ steps: "CLINICAL_REASONING", reasons: [unsupported] });
    if (change === "unknown reason") source.audit_trail[1].details = JSON.stringify({ steps: [], deferred: [], reasons: ["Unknown routing"], requires_escalation: true });
    if (change === "contradictory completion") source.audit_trail.push(event("CLINICAL_REASONING_COMPLETED"));
    if (change === "contradictory plan") { Object.assign(source, example(2)); const plan = JSON.parse(source.audit_trail[1].details!); plan.deferred = ["CLINICAL_REASONING"]; source.audit_trail[1].details = JSON.stringify(plan); }
    if (change === "completed but unsupported") { Object.assign(source, example(2)); const plan = JSON.parse(source.audit_trail[1].details!); plan.reasons = [unsupported]; source.audit_trail[1].details = JSON.stringify(plan); }
    if (change === "duplicate plan") source.audit_trail.push({ ...source.audit_trail[1], event_id: "duplicate" });
    if (change === "duplicate completion") { Object.assign(source, example(2)); source.audit_trail.push(event("CLINICAL_REASONING_COMPLETED")); }
    if (change === "conflicting reasons") { const plan = JSON.parse(source.audit_trail[1].details!); plan.reasons.push(administrative); source.audit_trail[1].details = JSON.stringify(plan); }
    if (change === "administrative event alone") source.audit_trail = [event("ADMINISTRATIVE_PREPARATION_ONLY")];
    expect(evaluationSummary(source, false)).toContainEqual(["Clinical evaluation", "Execution not recorded"]);
  });
  it("recognizes historical completed evaluations without a routing plan and labels demo honestly", () => {
    const source = example(5);
    source.audit_trail = source.audit_trail.filter(e => e.action !== "EXECUTION_PLANNED");
    expect(evaluationSummary(source, true)).toContainEqual(["Clinical evaluation", "Completed in saved evaluation - 5 criteria evaluated"]);
    expect(evaluationSummary(source, true)).toContainEqual(["Deterministic checks", "Completed in saved evaluation"]);
  });
  it("does not infer completion from results/readiness and handles document status conservatively", () => {
    const source = { ...example(5), audit_trail: [] };
    expect(evaluationSummary(source, false)).toContainEqual(["Deterministic checks", "Execution not recorded"]);
    expect(evaluationSummary(source, false)).toContainEqual(["Clinical evaluation", "Execution not recorded"]);
    source.insurance_results[0].status = "REQUIRES_HUMAN_REVIEW";
    expect(evaluationSummary(source, false)).toContainEqual(["Document checks", "Review required"]);
    source.insurance_results = [];
    expect(evaluationSummary(source, false)).toContainEqual(["Document checks", "Document checks not recorded"]);
  });
  it("preserves raw plan, identifiers, full criterion definitions and unknown event content", () => {
    const source = example(2);
    source.clinical_results[0] = { ...source.clinical_results[0], criterion_id: "gallstones_documented",
      criterion_name: "Complete original clinical definition", source_rule_id: "SAGES-SYMPTOMATIC-GALLSTONES-PROTOTYPE" };
    source.audit_trail.push(event("UNKNOWN_STAGE", "Unchanged unknown content."));
    render(<WorkspaceResult workspace={source} openSource={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Gallstones documented" })).toBeVisible();
    const criterion = screen.getByRole("heading", { name: "Gallstones documented" }).closest("article")!;
    fireEvent.click(within(criterion).getByText("Technical details"));
    expect(within(criterion).getByText("Complete original clinical definition")).toBeVisible();
    expect(within(criterion).getByText(/SAGES-SYMPTOMATIC-GALLSTONES-PROTOTYPE/)).toBeVisible();
    fireEvent.click(screen.getByText("Decision Trace"));
    expect(screen.getByText("Evaluation route selected")).toBeVisible();
    const route = screen.getByText("Evaluation route selected").closest("li")!;
    expect(within(route).getByText(/Clinical evaluation selected/)).toBeVisible();
    fireEvent.click(within(route).getByText("Technical details"));
    expect(within(route).getByText(source.audit_trail[1].details!)).toBeVisible();
    expect(screen.getByText("Unchanged unknown content.", { selector: "p" })).toBeVisible();
    expect(tracePresentation(event("EXECUTION_PLANNED", "not JSON")).summary).toContain("could not be interpreted");
  });
});
