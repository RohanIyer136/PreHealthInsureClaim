import type { DecisionWorkspace } from "../types/api";

type Event = DecisionWorkspace["audit_trail"][number];
type Plan = { steps: string[]; deferred: string[]; reasons: string[]; requires_escalation: boolean };
const unknown = "Execution not recorded";
const unsupported = "Clinical knowledge/capability for the requested service is unavailable; expert review is required.";
const unresolved = "Clinical retrieval did not resolve exactly one artifact; expert review is required.";
const administrative = "Explicit service configuration requires deterministic checks only.";
const terminal = "Configured terminal deterministic finding; clinical preparation deferred.";
const labels: Record<string, string> = {
  required_document_roles_present: "Required documents", required_document_types_present: "Required documents",
  policy_active_on_service_date: "Policy active on service date",
  symptomatic_gallstone_presentation: "Symptoms attributed to gallstones", gallstones_documented: "Gallstones documented",
};
export const findingTitle = (id: string, original: string) => labels[id] || original;
export function readableFinding(message: string): string {
  const index = message.indexOf(":");
  return index > 0 && labels[message.slice(0, index)] ? `${labels[message.slice(0, index)]}${message.slice(index)}` : message;
}
function planFor(event?: Event): Plan | null {
  try {
    const value = JSON.parse(event?.details || "null");
    const strings = (array: unknown): array is string[] => Array.isArray(array) && array.every(item => typeof item === "string");
    return value && strings(value.steps) && strings(value.deferred) && strings(value.reasons) &&
      typeof value.requires_escalation === "boolean" ? value : null;
  } catch { return null; }
}
export function evaluationSummary(workspace: DecisionWorkspace, demo: boolean) {
  const events = workspace.audit_trail;
  const has = (action: string) => events.some(event => event.action === action);
  const plans = events.filter(event => event.action === "EXECUTION_PLANNED");
  const plan = plans.length === 1 ? planFor(plans[0]) : null;
  let clinical = unknown;
  const completed = has("CLINICAL_REASONING_COMPLETED");
  const skipped = has("EVIDENCE_EXTRACTION_SKIPPED") || has("CLINICAL_RETRIEVAL_SKIPPED") || has("ADMINISTRATIVE_PREPARATION_ONLY");
  const invalid = plans.length > 1 || (plans.length === 1 && !plan) ||
    events.filter(event => event.action === "CLINICAL_REASONING_COMPLETED").length > 1 ||
    (plan && [unsupported, unresolved, administrative, terminal].filter(reason => plan.reasons.includes(reason)).length > 1);
  if (!invalid && completed && !skipped && workspace.clinical_results.length > 0 &&
      (!plan || (plan.steps.includes("CLINICAL_REASONING") && !plan.deferred.includes("CLINICAL_REASONING") &&
        ![unsupported, unresolved, administrative, terminal].some(reason => plan.reasons.includes(reason))))) {
    clinical = `${demo ? "Completed in saved evaluation" : "Completed with AI"} - ${workspace.clinical_results.length} criteria evaluated`;
  } else if (!invalid && !completed && !has("EVIDENCE_EXTRACTION_COMPLETED") && !workspace.clinical_results.length &&
      plan && !plan.steps.includes("CLINICAL_REASONING") && has("EVIDENCE_EXTRACTION_SKIPPED") &&
      (has("CLINICAL_RETRIEVAL_SKIPPED") || (has("CLINICAL_KNOWLEDGE_RETRIEVED") && plan.reasons.includes(unresolved)))) {
    if (plan.requires_escalation && plan.reasons.includes(unresolved) && plan.steps.includes("CLINICAL_RETRIEVAL") &&
        plan.deferred.includes("EVIDENCE_EXTRACTION") && plan.deferred.includes("CLINICAL_REASONING")) clinical = "Not supported - Expert review required";
    else if (plan.reasons.includes(terminal) && plan.deferred.includes("CLINICAL_REASONING")) clinical = "Skipped - Policy/coverage finding";
    else if (plan.requires_escalation && plan.reasons.includes(unsupported) && plan.deferred.includes("CLINICAL_REASONING")) clinical = "Not supported - Expert review required";
    else if (plan.reasons.includes(administrative) && !plan.deferred.length) clinical = "Not required - Administrative pathway";
  }
  const documents = workspace.insurance_results.filter(item => ["required_document_roles_present", "required_document_types_present"].includes(item.criterion_id));
  let documentState = "Document checks not recorded";
  if (documents.length) {
    if (documents.some(item => ["REQUIRES_HUMAN_REVIEW", "NOT_SATISFIED"].includes(item.status))) documentState = "Review required";
    else if (documents.some(item => item.status === "INSUFFICIENT_EVIDENCE")) {
      const missing = documents.find(item => item.status === "INSUFFICIENT_EVIDENCE")!;
      documentState = missing.explanation === "Missing required document roles: physiotherapy" ? "Physiotherapy report missing" :
        missing.explanation === "Missing required document roles: diagnostic_imaging" ? "Diagnostic imaging report missing" : "Required documents missing";
    } else if (documents.every(item => item.status === "SATISFIED")) documentState = "Required documents present";
    else if (documents.every(item => item.status === "NOT_APPLICABLE")) documentState = "Not applicable";
  }
  return [
    ["Deterministic checks", has("DETERMINISTIC_RULES_COMPLETED") ? (demo ? "Completed in saved evaluation" : "Completed") : unknown],
    ["Document checks", documentState], ["Clinical evaluation", clinical],
    ["Evidence gaps", workspace.missing_evidence.length ? "Missing information identified" : "No gaps recorded within evaluated scope"],
    ["Final authorization", "Human reviewer"],
  ];
}
const stages: Record<string, string> = {
  WORKSPACE_PROCESSING_STARTED: "Case processing started", DETERMINISTIC_RULES_COMPLETED: "Policy and document checks completed",
  EXECUTION_PLANNED: "Evaluation route selected", EVIDENCE_EXTRACTION_COMPLETED: "Clinical evidence extracted",
  EVIDENCE_EXTRACTION_SKIPPED: "Clinical evidence extraction skipped", CLINICAL_KNOWLEDGE_RETRIEVED: "Clinical guidance retrieved",
  CLINICAL_RETRIEVAL_SKIPPED: "Clinical guidance retrieval skipped", CLINICAL_REASONING_COMPLETED: "Clinical evaluation completed",
  ADMINISTRATIVE_PREPARATION_ONLY: "Administrative preparation only", WORKSPACE_ASSEMBLED: "Decision workspace prepared",
};
export function tracePresentation(event: Event) {
  const plan = event.action === "EXECUTION_PLANNED" ? planFor(event) : null;
  const routes: Record<string, string> = { [terminal]: "Clinical preparation skipped following a policy/coverage finding.",
    [unresolved]: "Clinical guidance did not resolve uniquely; expert review is required.",
    [unsupported]: "Clinical evaluation is not supported; expert review is required.", [administrative]: "Deterministic administrative checks only; clinical evaluation is not required.",
    "Explicit service configuration requires clinical evaluation.": "Clinical evaluation selected after policy and document checks." };
  return { title: stages[event.action] || event.action,
    summary: event.action === "EXECUTION_PLANNED" ? (plan ? routes[[terminal, unsupported, unresolved, administrative].find(reason => plan.reasons.includes(reason)) || plan.reasons[0]] || "Route recorded; inspect technical details for its scope." : "Route could not be interpreted; original details retained.") : event.details };
}
