# Synthetic Insurance Runtime Configuration

This area is executable configuration, not an evaluation manifest. All products
are fictional, synthetic, project-authored and prototype-only. They are not real
insurer contracts, clinical guidance, payment promises, or regulatory obligations.
No golden answers, case IDs, readiness labels, or model outputs are stored here.

`synthetic_insurance.json` contains six product templates and 19 explicit service
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
No additional cases are registered with the API, and no new clinical routes are enabled.

Supported findings use existing CriterionResult statuses and insurance provenance:
policy_active_on_service_date, requested_service_category_covered,
prior_authorization_required, service_intent_not_excluded,
required_document_roles_present, benefit_utilization_within_limit,
emergency_administrative_handling. Coverage, eligibility and explicit intent failures
are configured terminal; missing documents normally allow useful clinical preparation.
Emergency timing creates an exceptional review finding, never treatment selection,
permission to delay care, or a legal/compliance conclusion.

Administrative configuration now covers ORTH-01/02/03/04/06, SURG-01/03/06,
ONC-03/05/06, ACUTE-01/04/06, MED-01/02/05/06 and SPEC-01/02/03/04/06.
SURG-02 and ONC-04 share their paired service configuration as well.
The remaining service requirements need explicit configuration and safely escalate;
they are not silently declared complete. These are insurance preparation capabilities,
not claims that the 36 design records are executable authorization cases.

Deliberate limitations:
- Source design records are not materialized at runtime. Explicit service codes,
  authoritative role metadata, and member/policy context need a future source adapter.
- SPEC-01/02 supply visit counts but no dated ledger period. Execution requires an
  explicit ledger interval, matching units and policy period; tests provide clearly
  synthetic periods. No period is inferred from note prose or the developer clock.
- Clinical disease activity, treatment response, marker thresholds, medical necessity,
  or reconstructive eligibility cannot be established from document presence.
  MED-06 detects a missing specialist role, not missing clinical facts by parsing prose.
- No real-time member/network verification, monetary benefits, appeals, complex
  exceptions, emergency treatment triage, or real insurer interpretation is implemented.
- Runtime product terms intentionally copy minimum source policy facts; tests check
  parity to prevent drift. Future edits require deliberate product versioning.
- Existing demo artifacts are unchanged; absent optional fields remain absent in
  serialization so frozen source fingerprints continue to validate.
