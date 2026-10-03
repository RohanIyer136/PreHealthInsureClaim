"""Offline design contracts, separate input records, and golden specifications."""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.knowledge.clinical_retriever import ClinicalKnowledgeArtifact
from backend.models.schemas import DocumentType, ReadinessStatus, Sex
from evaluation.benchmark import ClinicalExpectations, StrictModel, Tag

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Family = Literal["ORTH", "SURG", "ONC", "ACUTE", "MED", "SPEC"]
PolicyID = Literal[
    "P1_ESSENTIAL", "P2_STANDARD", "P3_PREMIUM", "P4_FAMILY_PLUS",
    "P5_CHRONIC_CARE", "P6_RESTRICTED_LEGACY",
]
Category = Literal[
    "routine_outpatient", "advanced_imaging", "elective_surgery", "emergency_care",
    "inpatient_admission", "rehabilitation", "specialty_medication", "maternity",
    "dental", "chronic_care",
]
ServiceIntent = Literal[
    "therapeutic", "diagnostic", "cosmetic", "reconstructive", "routine_care",
    "rehabilitative", "maternity", "dental_implant",
]
DocumentRole = Literal[
    "clinical_note", "physiotherapy", "diagnostic_imaging", "pathology", "biomarker",
    "specialist_assessment", "hospital_summary", "functional_assessment", "utilization_statement",
]
DesignTag = Tag | Literal[
    "positive_control", "negative_control", "emergency", "urgent", "routine",
    "complete_evidence", "policy_conflict", "cross_policy", "benefit_limit",
    "reported_approval", "reconstructive_vs_cosmetic", "level_of_care",
    "future_domain_knowledge", "specialty_medication", "maternity", "dental",
    "unsupported_inference",
]
Challenge = Literal[
    "prompt_injection", "reported_approval", "cross_document_contradiction",
    "expired_policy", "irrelevant_information", "unsupported_inference",
]


class BenefitLimit(StrictModel):
    amount: int = Field(gt=0)
    unit: Literal["visits", "courses", "months"]
    period_months: int = Field(gt=0)


class Benefit(StrictModel):
    category: Category
    included: bool
    prior_authorization: bool
    limit: BenefitLimit | None = None
    documentation_requirements: list[DocumentRole] = Field(min_length=1)
    notes: Text


class Network(StrictModel):
    scope: Literal["restricted", "standard", "extended"]
    outside_network: Literal["review_required", "limited", "not_included_except_emergency_review"]


class EmergencyHandling(StrictModel):
    authorization_timing: Literal["retrospective_review", "expedited_review"]
    notes: Text


class FictionalPolicy(StrictModel):
    policy_id: PolicyID
    display_name: Text
    synthetic: Literal[True]
    fictional: Literal[True]
    wording_origin: Literal["project_authored"]
    version: str = Field(pattern=r"^\d+\.\d+$")
    description: Text
    effective_from: date
    effective_to: date
    network: Network
    prior_authorization_categories: list[Category]
    emergency_handling: EmergencyHandling
    benefits: list[Benefit] = Field(min_length=10, max_length=10)
    exclusions: list[Text] = Field(min_length=1)
    excluded_service_intents: list[ServiceIntent]
    disclaimers: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_product(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Policy effective dates are reversed")
        categories = [item.category for item in self.benefits]
        if len(set(categories)) != 10:
            raise ValueError("Every policy benefit category must occur once")
        if len(set(self.prior_authorization_categories)) != len(self.prior_authorization_categories):
            raise ValueError("Duplicate prior authorization categories")
        if set(self.prior_authorization_categories) != {
            item.category for item in self.benefits if item.prior_authorization
        }:
            raise ValueError("Prior authorization metadata disagrees with benefits")
        return self


class PolicyCatalog(StrictModel):
    schema_version: Literal["1.0"]
    policies: list[FictionalPolicy] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def unique_products(self):
        if len({item.policy_id for item in self.policies}) != 6:
            raise ValueError("Policy identifiers must be unique")
        return self


class Demographics(StrictModel):
    age: int = Field(ge=0, le=120)
    sex: Sex


class DesignService(StrictModel):
    name: Text
    category: Category
    specialty: Text
    intent: ServiceIntent


class DesignDocument(StrictModel):
    document_id: Text
    role: DocumentRole
    document_type: DocumentType
    date: date
    author_role: Text
    content: Text


class MissingInformation(StrictModel):
    document_roles: list[DocumentRole] = Field(default_factory=list)
    evidence: list[Text] = Field(default_factory=list)


class Utilization(StrictModel):
    rehabilitation_visits_used: int = Field(default=0, ge=0)
    requested_rehabilitation_visits: int | None = Field(default=None, gt=0)


class DesignCase(StrictModel):
    case_id: str = Field(pattern=r"^(ORTH|SURG|ONC|ACUTE|MED|SPEC)-0[1-6]$")
    synthetic: Literal[True]
    implementation_state: Literal["DESIGN_ONLY"]
    benchmark_family: Family
    scenario_description: Text
    patient: Demographics
    requested_service: DesignService
    urgency: Literal["routine", "urgent", "emergency", "time_critical"]
    severity: Literal["mild", "moderate", "severe", "critical"]
    service_date: date
    policy_id: PolicyID
    policy_utilization: Utilization
    submitted_documents: list[DesignDocument] = Field(min_length=1)
    intentionally_missing: MissingInformation
    benchmark_tags: list[DesignTag] = Field(min_length=1)
    robustness_challenges: list[Challenge] = Field(default_factory=list)
    existing_vertical_reference: Literal["PA-BENCH-006", "PA-DEMO-002"] | None = None

    @model_validator(mode="after")
    def coherent_case(self):
        if self.case_id.split("-")[0] != self.benchmark_family:
            raise ValueError("Case ID and family disagree")
        ids = [item.document_id for item in self.submitted_documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate submitted document ID")
        if set(self.intentionally_missing.document_roles) & {
            item.role for item in self.submitted_documents
        }:
            raise ValueError("Intentionally missing document role is submitted")
        if len(set(self.benchmark_tags)) != len(self.benchmark_tags):
            raise ValueError("Duplicate case tags")
        if self.existing_vertical_reference is not None and self.case_id not in {"ORTH-01", "ORTH-02"}:
            raise ValueError("Only the lumbar design controls may reference the existing vertical")
        return self


class DesignMatrix(StrictModel):
    schema_version: Literal["1.0"]
    cases: list[DesignCase] = Field(min_length=36, max_length=36)

    @model_validator(mode="after")
    def complete_matrix(self):
        if len({item.case_id for item in self.cases}) != 36:
            raise ValueError("Case identifiers must be unique")
        if Counter(item.benchmark_family for item in self.cases) != dict.fromkeys(
            ["ORTH", "SURG", "ONC", "ACUTE", "MED", "SPEC"], 6
        ):
            raise ValueError("Each of the six families must have six cases")
        return self


class EvidenceTarget(StrictModel):
    # Design taxonomy, not an expansion of production EvidenceConcept.
    concept: Literal[
        "LOW_BACK_PAIN", "SYMPTOM_DURATION", "CONSERVATIVE_MANAGEMENT",
        "INTERVENTION_OR_SPECIALIST_PLANNING", "OTHER_CLINICAL_EVIDENCE",
        "DIAGNOSIS_DOCUMENTATION", "PATHOLOGY_DOCUMENTATION", "BIOMARKER_DOCUMENTATION",
        "SEVERITY_DOCUMENTATION", "FUNCTIONAL_IMPACT", "TREATMENT_HISTORY",
        "LEVEL_OF_CARE_DOCUMENTATION", "PREGNANCY_DOCUMENTATION", "DOCUMENTED_REQUEST",
    ]
    meaning: Text
    source_document_ids: list[Text] = Field(min_length=1)


class ExpectedConflict(StrictModel):
    source_document_ids: list[Text] = Field(min_length=2)
    topic: Text


class EvaluationSpec(StrictModel):
    case_id: Text
    benchmark_family: Family
    capability_under_test: list[Text] = Field(min_length=1)
    knowledge_status: Literal["existing_vertical_reference", "requires_future_domain_knowledge"]
    knowledge_limitation: Text
    expected_readiness: ReadinessStatus | None
    clinical: ClinicalExpectations | None
    expected_missing_documents: list[DocumentRole]
    expected_missing_information: list[Text]
    expected_conflicts: list[ExpectedConflict]
    expected_policy_findings: list[Literal[
        "prior_authorization_review_required", "routine_authorization_not_required",
        "service_category_excluded", "policy_outside_effective_dates",
        "rehabilitation_within_limit", "rehabilitation_limit_exceeded",
        "reconstructive_intent_review",
        "service_intent_excluded",
    ]]
    required_evidence_concepts: list[EvidenceTarget] = Field(min_length=1)
    forbidden_inferences: list[Text] = Field(min_length=1)
    expected_escalation_behavior: Literal[
        "future_domain_knowledge_required", "surface_conflict_for_human_review",
        "policy_review_required", "documentation_review_required", "implementation_required",
    ]
    expected_emergency_behavior: Literal[
        "not_applicable", "fictional_emergency_pathway_review", "fictional_time_critical_pathway_review",
    ]

    @model_validator(mode="after")
    def no_unbacked_clinical_answers(self):
        if self.knowledge_status == "requires_future_domain_knowledge" and (
            self.clinical is not None or self.expected_readiness is not None
        ):
            raise ValueError("Future domains cannot carry clinical statuses or readiness labels")
        return self


class Comparison(StrictModel):
    comparison_id: Text
    baseline_case_id: Text
    variant_case_id: Text
    comparison_dimension: Literal["missing_document", "policy", "utilization"]
    purpose: Text


class EvaluationMatrix(StrictModel):
    schema_version: Literal["1.0"]
    cases: list[EvaluationSpec] = Field(min_length=36, max_length=36)
    comparisons: list[Comparison] = Field(min_length=5)

    @model_validator(mode="after")
    def unique_references(self):
        if len({item.case_id for item in self.cases}) != 36:
            raise ValueError("Duplicate evaluation case IDs")
        if len({item.comparison_id for item in self.comparisons}) != len(self.comparisons):
            raise ValueError("Duplicate comparison IDs")
        pairs = [(item.baseline_case_id, item.variant_case_id) for item in self.comparisons]
        if len(set(pairs)) != len(pairs):
            raise ValueError("Duplicate comparison pairs")
        return self


def validate_foundation(
    inputs: DesignMatrix, catalog: PolicyCatalog, golden: EvaluationMatrix,
    knowledge: list[ClinicalKnowledgeArtifact],
) -> None:
    cases = {item.case_id: item for item in inputs.cases}
    policies = {item.policy_id: item for item in catalog.policies}
    artifacts = {item.knowledge_id: item for item in knowledge}
    if set(cases) != {item.case_id for item in golden.cases}:
        raise ValueError("Input and evaluation case IDs differ")
    for case in inputs.cases:
        if case.policy_id not in policies:
            raise ValueError("Unknown policy reference")
        if any(doc.date > case.service_date for doc in case.submitted_documents):
            raise ValueError("Submitted document is dated after the service date")
    for spec in golden.cases:
        case = cases[spec.case_id]
        if spec.benchmark_family != case.benchmark_family:
            raise ValueError("Evaluation family mismatch")
        if set(spec.expected_missing_documents) != set(case.intentionally_missing.document_roles):
            raise ValueError("Missing-document specification disagrees with input")
        ids = {doc.document_id for doc in case.submitted_documents}
        for target in [*spec.required_evidence_concepts, *spec.expected_conflicts]:
            if len(set(target.source_document_ids)) != len(target.source_document_ids):
                raise ValueError("Duplicate evidence source references")
            if not set(target.source_document_ids) <= ids:
                raise ValueError("Evidence target references an unsubmitted source")
        if spec.knowledge_status == "existing_vertical_reference":
            if case.existing_vertical_reference is None or spec.clinical is None:
                raise ValueError("Existing-vertical scoring requires a backed clinical reference")
        if spec.clinical is not None:
            artifact = artifacts.get(spec.clinical.knowledge_id)
            if artifact is None:
                raise ValueError("Unknown clinical knowledge artifact")
            valid = {item.criterion_id for item in artifact.criteria_for_future_evaluation}
            for criterion in spec.clinical.criteria:
                if criterion.criterion_id not in valid or not set(criterion.source_document_ids) <= ids:
                    raise ValueError("Invalid clinical criterion or source reference")
        policy = policies[case.policy_id]
        benefit = next(item for item in policy.benefits if item.category == case.requested_service.category)
        findings = set(spec.expected_policy_findings)
        inactive = not policy.effective_from <= case.service_date <= policy.effective_to
        if ("expired_policy" in case.robustness_challenges) != inactive:
            raise ValueError("Expired-policy challenge and service dates disagree")
        if ("policy_outside_effective_dates" in findings) != inactive:
            raise ValueError("Policy effective-date finding disagrees with source dates")
        for finding, condition in [
            ("service_category_excluded", not benefit.included),
            ("prior_authorization_review_required", benefit.prior_authorization),
            ("routine_authorization_not_required", not benefit.prior_authorization),
            ("service_intent_excluded", case.requested_service.intent in policy.excluded_service_intents),
        ]:
            if finding in findings and not condition:
                raise ValueError("Policy finding disagrees with fictional policy")
        if findings & {"rehabilitation_within_limit", "rehabilitation_limit_exceeded"}:
            usage = case.policy_utilization
            if benefit.limit is None or benefit.limit.unit != "visits" or usage.requested_rehabilitation_visits is None:
                raise ValueError("Rehabilitation comparison requires a visit limit and utilization")
            exceeded = usage.rehabilitation_visits_used + usage.requested_rehabilitation_visits > benefit.limit.amount
            correct = "rehabilitation_limit_exceeded" if exceeded else "rehabilitation_within_limit"
            if findings & {"rehabilitation_within_limit", "rehabilitation_limit_exceeded"} != {correct}:
                raise ValueError("Rehabilitation finding disagrees with visit counts")
        emergency = case.urgency in {"emergency", "time_critical"}
        if (spec.expected_emergency_behavior != "not_applicable") != emergency:
            raise ValueError("Emergency evaluation and input urgency disagree")
    if not any(item.comparison_dimension == "policy" for item in golden.comparisons):
        raise ValueError("At least one cross-policy comparison is required")
    for pair in golden.comparisons:
        if pair.baseline_case_id not in cases or pair.variant_case_id not in cases:
            raise ValueError("Unknown paired-case reference")
        left, right = cases[pair.baseline_case_id], cases[pair.variant_case_id]
        for field in ("benchmark_family", "patient", "requested_service", "urgency", "severity", "service_date"):
            if getattr(left, field) != getattr(right, field):
                raise ValueError("Controlled comparison changes a fixed clinical input")
        if pair.comparison_dimension != "policy" and left.policy_id != right.policy_id:
            raise ValueError("Non-policy comparison changes policy")
        if pair.comparison_dimension != "utilization" and left.policy_utilization != right.policy_utilization:
            raise ValueError("Non-utilization comparison changes utilization")
        if pair.comparison_dimension == "missing_document":
            baseline = {doc.document_id: doc for doc in left.submitted_documents}
            variant = {doc.document_id: doc for doc in right.submitted_documents}
            removed = baseline.keys() - variant.keys()
            if len(removed) != 1 or variant.keys() - baseline.keys() or any(
                doc != baseline[identifier] for identifier, doc in variant.items()
            ):
                raise ValueError("Missing-document comparison must remove only one unchanged source")
            role = baseline[next(iter(removed))].role
            if set(right.intentionally_missing.document_roles) != set(left.intentionally_missing.document_roles) | {role}:
                raise ValueError("Removed source role must be identified as missing")
        elif left.submitted_documents != right.submitted_documents or left.intentionally_missing != right.intentionally_missing:
            raise ValueError("Policy/utilization comparison must keep clinical evidence constant")
        elif pair.comparison_dimension == "policy" and left.policy_id == right.policy_id:
            raise ValueError("Cross-policy comparison must change policy")
        elif pair.comparison_dimension == "utilization" and left.policy_utilization == right.policy_utilization:
            raise ValueError("Utilization comparison must change utilization")


def load_design_inputs(path: Path) -> DesignMatrix:
    return DesignMatrix.model_validate_json(path.read_text(encoding="utf-8"))


def load_policy_catalog(path: Path) -> PolicyCatalog:
    return PolicyCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def load_evaluation_specs(path: Path) -> EvaluationMatrix:
    return EvaluationMatrix.model_validate_json(path.read_text(encoding="utf-8"))
