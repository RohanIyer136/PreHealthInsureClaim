export type CriterionStatus =
  | "SATISFIED"
  | "NOT_SATISFIED"
  | "INSUFFICIENT_EVIDENCE"
  | "NOT_APPLICABLE"
  | "REQUIRES_HUMAN_REVIEW";
export type ReadinessStatus =
  | "PROCESSING"
  | "READY_FOR_EXPERT_REVIEW"
  | "EVIDENCE_REQUIRED"
  | "HUMAN_REVIEW_REQUIRED";
export interface RequestedService {
  service_code: string;
  service_name: string;
  category: string;
  diagnosis_code: string | null;
  diagnosis_description: string;
  priority: "ROUTINE" | "URGENT";
}
export interface Authorization {
  authorization_id: string;
  patient_id: string;
  policy_id: string;
  requested_service: RequestedService;
  requesting_provider: string;
  submitted_document_ids: string[];
  submitted_at: string;
  status: string;
}
export interface CaseSummary {
  authorization_id: string;
  patient_id: string;
  requested_service: RequestedService;
  priority: "ROUTINE" | "URGENT";
  submitted_at: string;
  status: string;
  submitted_document_count: number;
}
export interface ClinicalDocument {
  document_id: string;
  patient_id: string;
  document_type: string;
  date: string;
  author_role: string;
  content: string;
  source_system: string;
}
export interface CaseDetail {
  authorization: Authorization;
  patient: {
    patient_id: string;
    age: number;
    sex: string;
    member_id: string;
    policy_id: string;
  };
  policy: {
    policy_id: string;
    insurer_name: string;
    plan_name: string;
    member_id: string;
    coverage_status: string;
    effective_date: string;
    expiry_date: string;
    benefits: string[];
    exclusions: string[];
    prior_authorization_required: boolean;
    policy_document_id: string;
  };
  documents: ClinicalDocument[];
}
export interface EvidenceItem {
  evidence_id: string;
  source_document_id: string;
  source_type: string;
  excerpt: string;
  concept: string;
  value: string;
  confidence: number;
  uncertainty: string | null;
  extraction_method: string;
  location: string | null;
  relevance: string | null;
}
export interface CriterionResult {
  criterion_id: string;
  criterion_name: string;
  domain: "CLINICAL" | "INSURANCE" | "REGULATORY";
  status: CriterionStatus;
  explanation: string;
  evidence: EvidenceItem[];
  confidence: number | null;
  source_rule_id: string | null;
}
export interface DecisionWorkspace {
  workspace_id: string;
  authorization_id: string;
  clinical_results: CriterionResult[];
  insurance_results: CriterionResult[];
  regulatory_results: CriterionResult[];
  missing_evidence: string[];
  conflicts: string[];
  overall_confidence: number | null;
  readiness_status: ReadinessStatus;
  generated_at: string;
  audit_trail: {
    event_id: string;
    timestamp: string;
    actor: string;
    action: string;
    details: string | null;
  }[];
}
