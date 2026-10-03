import type {
  CaseDetail,
  CaseSummary,
  DecisionWorkspace,
  EvidenceItem,
} from "../types/api";

export const detail: CaseDetail = {
  authorization: {
    authorization_id: "CASE-101",
    patient_id: "PATIENT-101",
    policy_id: "POLICY-101",
    requested_service: {
      service_code: "MRI",
      service_name: "MRI Lumbar Spine",
      category: "Diagnostic imaging",
      diagnosis_code: null,
      diagnosis_description: "Synthetic lower-back symptoms",
      priority: "ROUTINE",
    },
    requesting_provider: "Synthetic Clinic",
    submitted_document_ids: ["NOTE-101"],
    submitted_at: "2026-10-01T09:00:00Z",
    status: "SUBMITTED",
  },
  patient: {
    patient_id: "PATIENT-101",
    age: 46,
    sex: "UNKNOWN",
    member_id: "MEMBER-101",
    policy_id: "POLICY-101",
  },
  policy: {
    policy_id: "POLICY-101",
    insurer_name: "Synthetic Insurer",
    plan_name: "Test Plan",
    member_id: "MEMBER-101",
    coverage_status: "ACTIVE",
    effective_date: "2026-01-01",
    expiry_date: "2026-12-31",
    benefits: ["Diagnostic imaging"],
    exclusions: [],
    prior_authorization_required: true,
    policy_document_id: "POLICY-DOC-101",
  },
  documents: [
    {
      document_id: "NOTE-101",
      patient_id: "PATIENT-101",
      document_type: "CLINICAL_NOTE",
      date: "2026-10-01",
      author_role: "Synthetic Clinician",
      content:
        "Symptoms persist. Six weeks of physiotherapy completed. Further assessment requested.",
      source_system: "Synthetic EHR",
    },
  ],
};
export const secondDetail: CaseDetail = {
  ...detail,
  authorization: { ...detail.authorization, authorization_id: "CASE-102" },
};
export const cases: CaseSummary[] = [detail, secondDetail].map((item) => ({
  authorization_id: item.authorization.authorization_id,
  patient_id: item.patient.patient_id,
  requested_service: item.authorization.requested_service,
  priority: item.authorization.requested_service.priority,
  submitted_at: item.authorization.submitted_at,
  status: item.authorization.status,
  submitted_document_count: item.documents.length,
}));
export const evidence: EvidenceItem = {
  evidence_id: "EVIDENCE-101",
  source_document_id: "NOTE-101",
  source_type: "CLINICAL_NOTE",
  concept: "PHYSIOTHERAPY_HISTORY",
  value: "Six weeks completed",
  excerpt: "Six weeks of physiotherapy completed.",
  confidence: 0.9,
  uncertainty: "Treatment frequency not stated.",
  extraction_method: "offline-fixture",
  location: null,
  relevance: null,
};
export const workspace: DecisionWorkspace = {
  workspace_id: "WORKSPACE-101",
  authorization_id: "CASE-101",
  generated_at: "2026-10-01T10:00:00Z",
  readiness_status: "EVIDENCE_REQUIRED",
  overall_confidence: null,
  insurance_results: [
    {
      criterion_id: "documents",
      criterion_name: "Required documents",
      domain: "INSURANCE",
      status: "INSUFFICIENT_EVIDENCE",
      explanation: "Physiotherapy report missing.",
      evidence: [],
      confidence: null,
      source_rule_id: "POLICY-SOURCE",
    },
  ],
  clinical_results: [
    {
      criterion_id: "management",
      criterion_name: "Conservative management",
      domain: "CLINICAL",
      status: "SATISFIED",
      explanation: "Cited note documents a course of treatment.",
      evidence: [evidence],
      confidence: 0.9,
      source_rule_id: "GUIDANCE-101",
    },
  ],
  regulatory_results: [],
  missing_evidence: ["Physiotherapy report required."],
  conflicts: ["Treatment dates require reconciliation."],
  audit_trail: [
    {
      event_id: "EVENT-101",
      action: "WORKSPACE_PROCESSING_COMPLETED",
      timestamp: "2026-10-01T10:00:00Z",
      actor: "workspace-service",
      details: "Synthetic test event.",
    },
  ],
};
