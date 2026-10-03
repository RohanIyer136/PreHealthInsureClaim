# Synthetic Insurance Runtime Configuration

This area is executable configuration, not an evaluation manifest. All products
are fictional, synthetic, project-authored and prototype-only. They are not real
insurer contracts, clinical guidance, payment promises, or regulatory obligations.
No golden answers, case IDs, readiness labels, or model outputs are stored here.

`synthetic_insurance.json` contains six product templates and 30 explicit service
document configurations. The broad imaging PT requirement is scoped to IMG-MRI-LS,
not every imaging request. Templates bind to caller-supplied policy/member IDs via
`SyntheticProduct.for_member`; that does not verify independent member eligibility.
The existing InsurancePolicy remains the policy/member contract. Optional structured
terms extend it rather than introducing a second policy/member model.

`InsuranceRequestContext` supplies service date, explicit intent and urgency,
submitted-source role assignments, and optional utilization. Role metadata must
come from an authoritative source adapter, not clinical-text guesses or an LLM.
Role assignments are checked against submitted IDs, patient IDs and document types;
pathology and biomarker remain distinct despite sharing LAB_RESULT.

The production builder installs DeterministicInsuranceEvaluator inside the existing
DecisionWorkspaceService. Legacy inputs without both optional extensions use the
unchanged legacy deterministic rules. If only one extension is present, the evaluator
requires review rather than guessing or silently falling back. Missing service
requirements and unknown benefit categories likewise require review. Structured
terms control category-specific findings; legacy summary fields are not substitutes.
The existing repository also loads `synthetic_data/runtime_cases.json`; 36 additional
synthetic source cases are registered with the same API. Only `IMG-MRI-LS` and
`SURG-CHOLECYSTECTOMY` enable clinical execution. The latter uses a narrow prototype
of SAGES section III symptomatic gallstone guidance, not full surgical eligibility.
See the root README for the clinical source and `synthetic_data/RUNTIME_CASES.md`
for case-source provenance. Unsupported clinical domains still escalate without AI.

Supported findings use existing CriterionResult statuses and insurance provenance:
policy_active_on_service_date, requested_service_category_covered,
prior_authorization_required, service_intent_not_excluded,
required_document_roles_present, benefit_utilization_within_limit,
emergency_administrative_handling. Coverage, eligibility and explicit intent failures
are configured terminal; missing documents normally allow useful clinical preparation.
Emergency timing creates an exceptional review finding, never treatment selection,
permission to delay care, or a legal/compliance conclusion.

Administrative configuration covers all promoted service codes with category-level
document requirements and represented service-specific additions. Unsupported
clinical services still require human review: basic document completeness is not
clinical sufficiency or medical necessity. Capability profiles separate a requirement
for clinical knowledge from availability of clinical execution. These are insurance
preparation capabilities, not new medical-necessity knowledge.

Deliberate limitations:
- Runtime records are a checked-in source-only snapshot; production never reads design
  records. Real source adapters and authoritative member/role verification remain future work.
- SPEC-01/02 supply visit counts but no dated ledger period. Execution requires an
  explicit ledger interval, matching units and policy period. Promoted records declare
  a new synthetic 2026 ledger period, documented in RUNTIME_CASES.md. No evaluator
  period is inferred from note prose or the developer clock.
- Clinical disease activity, treatment response, marker thresholds, medical necessity,
  or reconstructive eligibility cannot be established from document presence.
  MED-06 detects a missing specialist role, not missing clinical facts by parsing prose.
- No real-time member/network verification, monetary benefits, appeals, complex
  exceptions, emergency treatment triage, or real insurer interpretation is implemented.
- Runtime product terms intentionally copy minimum source policy facts; tests check
  parity to prevent drift. Future edits require deliberate product versioning.
- Existing demo artifacts are unchanged; absent optional fields remain absent in
  serialization so frozen source fingerprints continue to validate.
