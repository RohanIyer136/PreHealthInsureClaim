"""One reusable deterministic evaluator for structured synthetic insurance terms."""

from collections.abc import Iterable

from backend.models.insurance import DocumentRole, InsuranceUrgency, ServiceDocumentRequirements
from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, CoverageStatus, CriterionDomain,
    CriterionResult, CriterionStatus, InsurancePolicy,
)
from backend.services.decision_workspace import DefaultDeterministicEvaluator


_ROLE_TYPES = {
    DocumentRole.CLINICAL_NOTE: {"CLINICAL_NOTE"},
    DocumentRole.PHYSIOTHERAPY: {"PHYSIOTHERAPY_REPORT"},
    DocumentRole.DIAGNOSTIC_IMAGING: {"IMAGING_REPORT"},
    DocumentRole.PATHOLOGY: {"LAB_RESULT"},
    DocumentRole.BIOMARKER: {"LAB_RESULT"},
    DocumentRole.SPECIALIST_ASSESSMENT: {"REFERRAL", "CLINICAL_NOTE"},
    DocumentRole.HOSPITAL_SUMMARY: {"DISCHARGE_SUMMARY"},
    DocumentRole.FUNCTIONAL_ASSESSMENT: {"CLINICAL_NOTE", "PHYSIOTHERAPY_REPORT"},
    DocumentRole.UTILIZATION_STATEMENT: {"CLINICAL_NOTE"},
}


class DeterministicInsuranceEvaluator(DefaultDeterministicEvaluator):
    """Extend legacy rules without changing existing lumbar source contracts."""

    def __init__(self, *args, service_requirements: Iterable[ServiceDocumentRequirements] = (), **kwargs):
        super().__init__(*args, **kwargs)
        requirements = tuple(service_requirements)
        self._services = {item.service_code: item for item in requirements}
        if len(self._services) != len(requirements):
            raise ValueError("Duplicate service document requirement codes")

    def evaluate(self, authorization: AuthorizationRequest, policy: InsurancePolicy,
                 documents: list[ClinicalDocument]) -> list[CriterionResult]:
        terms, context = policy.structured_terms, authorization.insurance_context
        if terms is None and context is None:
            return super().evaluate(authorization, policy, documents)
        source = terms.source_id if terms else policy.policy_document_id

        def finding(identifier, status, explanation, reference=source):
            return CriterionResult(criterion_id=identifier, criterion_name=identifier.replace("_", " ").capitalize(),
                                   domain=CriterionDomain.INSURANCE, status=status,
                                   explanation=explanation, source_rule_id=reference)

        if terms is None or context is None:
            return [finding("insurance_context_complete", CriterionStatus.REQUIRES_HUMAN_REVIEW,
                            "Structured policy terms and insurance request context are both required.")]
        active = (policy.coverage_status is CoverageStatus.ACTIVE
                  and policy.effective_date <= context.service_date <= policy.expiry_date)
        results = [finding("policy_active_on_service_date",
                           CriterionStatus.SATISFIED if active else CriterionStatus.NOT_SATISFIED,
                           f"Structured policy status and coverage dates evaluated for service date {context.service_date}.")]
        benefit = terms.category_benefits.get(authorization.requested_service.category)
        results.append(finding("requested_service_category_covered",
                               CriterionStatus.REQUIRES_HUMAN_REVIEW if benefit is None else
                               CriterionStatus.SATISFIED if benefit.included else CriterionStatus.NOT_SATISFIED,
                               "Service category is not represented; expert review is required." if benefit is None else
                               "Structured category inclusion evaluated; this is not clinical appropriateness."))
        excluded = context.service_intent in terms.excluded_service_intents
        results.append(finding("service_intent_not_excluded",
                               CriterionStatus.NOT_SATISFIED if excluded else CriterionStatus.SATISFIED,
                               f"Structured intent {context.service_intent.value} evaluated against explicit intent exclusions."))
        emergency = context.urgency in {InsuranceUrgency.EMERGENCY, InsuranceUrgency.TIME_CRITICAL}
        emergency_finding = finding(
            "emergency_administrative_handling",
            CriterionStatus.REQUIRES_HUMAN_REVIEW if emergency else CriterionStatus.NOT_APPLICABLE,
            f"Fictional {terms.emergency_authorization_timing} administrative pathway; never delay care or infer treatment eligibility or payment."
            if emergency else "Structured urgency does not select an emergency administrative pathway.",
        )
        if benefit is None:
            return [*results, emergency_finding]
        results.append(finding("prior_authorization_required",
                               CriterionStatus.SATISFIED if benefit.prior_authorization else CriterionStatus.NOT_APPLICABLE,
                               "Product requires prior authorization for this category." if benefit.prior_authorization else
                               "Product does not require ordinary prior authorization for this category."))

        requirement = self._services.get(authorization.requested_service.service_code)
        if requirement is None or requirement.category != authorization.requested_service.category:
            results.append(finding("required_document_roles_present", CriterionStatus.REQUIRES_HUMAN_REVIEW,
                                   "Service-scoped document requirements are not configured; expert review is required."))
        else:
            submitted_ids = set(authorization.submitted_document_ids)
            by_id = {doc.document_id: doc for doc in documents if doc.document_id in submitted_ids}
            roles = context.document_roles
            valid_roles = (set(roles) == set(by_id) == submitted_ids and all(
                by_id[identifier].patient_id == authorization.patient_id
                and by_id[identifier].document_type.value in _ROLE_TYPES[role]
                for identifier, role in roles.items()
            ))
            if not valid_roles:
                results.append(finding("required_document_roles_present", CriterionStatus.REQUIRES_HUMAN_REVIEW,
                                       "Submitted document role metadata is missing or inconsistent.", requirement.source_id))
            else:
                required = set(benefit.required_document_roles) | set(requirement.required_document_roles)
                missing = sorted(role.value for role in required - set(roles.values()))
                results.append(finding("required_document_roles_present",
                                       CriterionStatus.INSUFFICIENT_EVIDENCE if missing else CriterionStatus.SATISFIED,
                                       "Missing required document roles: " + ", ".join(missing) if missing else
                                       "Configured document roles are present; document presence does not establish clinical facts.",
                                       requirement.source_id + ";" + source))

        if not benefit.included or benefit.limit is None:
            results.append(finding("benefit_utilization_within_limit", CriterionStatus.NOT_APPLICABLE,
                                   "No utilization check applies to an excluded category or a benefit without a represented limit."))
        else:
            usage, limit = context.utilization, benefit.limit
            if (usage is None or usage.unit != limit.unit or usage.period_months != limit.period_months
                    or not usage.period_start <= context.service_date <= usage.period_end):
                results.append(finding("benefit_utilization_within_limit", CriterionStatus.REQUIRES_HUMAN_REVIEW,
                                       "Matching structured utilization and benefit-period context are required; no usage was inferred."))
            else:
                total = usage.used + usage.requested
                results.append(finding("benefit_utilization_within_limit",
                                       CriterionStatus.SATISFIED if total <= limit.amount else CriterionStatus.NOT_SATISFIED,
                                       f"{usage.used} used + {usage.requested} requested = {total} {limit.unit}; limit {limit.amount} in the supplied period."))
        results.append(emergency_finding)
        return results
