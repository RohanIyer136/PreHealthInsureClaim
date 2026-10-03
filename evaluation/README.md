# Synthetic Authorization Benchmark

The separate [multi-domain design foundation](MULTIDOMAIN.md) adds 36 design-only
scenarios and six fictional policy products. It does not replace this implemented
lumbar benchmark, change its answers, or expand production clinical coverage.

This benchmark is synthetic developer evaluation data, not evidence of clinical
efficacy or regulatory validation. `golden_cases.json` holds expected truth;
model responses, scores, and runtime results must be separate artifacts. Nothing
in `backend/` may import evaluation code or read golden expectations. A future
runner must pass only normal source documents, evidence, and retrieved knowledge
to production components. Expectations are used only after execution for scoring.

## Contract

`evaluation.benchmark.Benchmark` is the versioned, strict Pydantic contract.
`load_benchmark()` validates structure; `validate_references()` checks actual
authorization, submitted-document/patient, service/knowledge, and criterion links.
No dependency or production behavior changes are required.

Each materialized case has a stable `case_id`, authorization reference, original
scenario label, purpose, primary category, tags, explicit document requirements,
and an `expectations` object with independently optional layers:

- `evidence.required` / `evidence.forbidden`: concept plus semantic `meaning`,
  source documents, and optional ambiguity/approximation requirement. Each listed
  document is independently in scope. A required rule means the stated behavior
  must be represented for each source; a forbidden rule forbids the stated meaning
  in each source, not every extraction of that concept. Do not compare generated
  IDs, exact prose, counts, uncertainty labels, or confidence numbers.
- `clinical`: referenced knowledge artifact and selected criterion statuses.
  Listed sources must appear among cited evidence sources; extra legitimate
  citations are permitted. Empty sources impose no citation requirement. Only
  listed criteria are scored; omitted criteria are unscored, not absent results.
  Production validation still requires complete criterion coverage.
- `workflow`: readiness and required missing-document, missing-clinical-criterion,
  and conflict-criterion conditions. These lists are required subsets, not exact
  prose or exhaustive lists. `findings` preserves the original scenario markers.
  Document requirements are benchmark evaluator configuration, not clinical AI
  expectations. Conflicts take precedence over missing evidence in the existing
  workspace service. No authorization approve/deny expectation exists.

Stable categories are `clinical`, `insurance`, `adversarial`, `orchestration`.
The closed `Tag` vocabulary in `benchmark.py` identifies individual behaviors;
cases may span categories using multiple tags. Additions require an intentional
contract update. Clinical statuses and readiness reuse existing domain enums;
`NOT_APPLICABLE` remains excluded from clinical reasoning as in production.

## Migration

The original five authorization references, scenario labels, source data, and
findings are retained. They now have evidence and selected clinical expectations.
PA-DEMO-001 is complete **documentation**, not proven candidacy: neither NOTE-001
nor PT-001 establishes surgery/intervention candidacy. Its clinical expectation
is `INSUFFICIENT_EVIDENCE` and readiness is corrected from
`READY_FOR_EXPERT_REVIEW` to `EVIDENCE_REQUIRED`, following the unchanged workspace
rules. PA-BENCH-006 is the complete explicit-candidacy positive control below.
Cases 002-005 keep their original readiness; absent candidacy is explicitly
represented without masking missing documents, policy expiry, ambiguity, or conflict.

## Coverage Matrix

28 slots total: 19 MATERIALIZED synthetic golden cases and 9 COVERED offline
fixture slots. No matrix slots are deferred. Slot numbers are not authorization
IDs. E = extraction, C = clinical reasoning, W = workflow/deterministic behavior.
Fixture slots reference existing tests unless a software-coverage gap required a
new fixture. They are not fabricated patient records. Counts describe coverage,
not measured model performance. Synthetic cases use reviewed source statements
and selected expectations; case-specific document requirements are explicit
evaluator configuration, not inferred from note text or passed to the AI.

| Slot | State / Source | Category | Tags | Layers | Named behavior |
|---|---|---|---|---|---|
| 01 | MATERIALIZED PA-DEMO-001 | clinical | complete_documents, cross_document_evidence, intervention_candidacy | E/C/W | Complete documents do not prove candidacy |
| 02 | MATERIALIZED PA-DEMO-002 | orchestration | missing_required_document | E/W | Unsubmitted physiotherapy report cannot be used |
| 03 | MATERIALIZED PA-DEMO-003 | insurance | expired_policy | W | Expiry at submission blocks routine readiness |
| 04 | MATERIALIZED PA-DEMO-004 | clinical | ambiguous_wording, missing_clinical_evidence | E/C/W | Preserve materially ambiguous duration |
| 05 | MATERIALIZED PA-DEMO-005 | clinical | cross_document_contradiction, conflicting_treatment_duration | E/C/W | Conflicting treatment histories require review |
| 06 | MATERIALIZED PA-BENCH-006 | clinical | complete_documents, explicit_candidacy | E/C/W | Explicit sufficient evidence for every criterion; positive control |
| 07 | MATERIALIZED PA-BENCH-007 | clinical | missing_clinical_evidence | E/C/W | Undocumented treatment history yields insufficient evidence |
| 08 | MATERIALIZED PA-BENCH-008 | clinical | explicit_contrary_evidence | E/C | Explicit non-candidacy supports NOT_SATISFIED |
| 09 | MATERIALIZED PA-BENCH-009 | clinical | approximate_duration | E/C | Approximation survives the approximate-duration criterion |
| 10 | MATERIALIZED PA-BENCH-010 | clinical | negation | E/C | Negated radicular symptoms do not become positive findings |
| 11 | MATERIALIZED PA-BENCH-011 | clinical | historical_treatment | E/C | Previous resolved-episode treatment is not current management |
| 12 | MATERIALIZED PA-BENCH-012 | clinical | temporal_confusion | E/C | Eight-week symptoms do not inflate two-week treatment |
| 13 | MATERIALIZED PA-BENCH-013 | clinical | cross_document_evidence | E/C | Complementary note, PT, and referral support distinct facts |
| 14 | MATERIALIZED PA-BENCH-014 | clinical | cross_document_contradiction | E/C/W | Opposing neurological findings and explicit candidacy assessments require review |
| 15 | MATERIALIZED PA-BENCH-015 | clinical | irrelevant_information | E/C | Historical wrist therapy does not establish lumbar management |
| 16 | MATERIALIZED PA-BENCH-016 | adversarial | prompt_injection | E/C | Pasted chatbot comment stays data; surrounding facts remain usable |
| 17 | COVERED fixture F17 | orchestration | wrong_patient | W | Reject wrong-patient source before AI execution |
| 18 | COVERED fixture F18 | orchestration | duplicate_document | W | Reject duplicate submitted document IDs |
| 19 | MATERIALIZED PA-BENCH-019 | insurance | uncovered_service | W | Dental-only benefit does not cover diagnostic imaging |
| 20 | COVERED fixture F20 | insurance | prior_authorization | W | Required prior authorization recorded without approval |
| 21 | COVERED fixture F21 | insurance | prior_authorization | W | Not-required prior authorization uses NOT_APPLICABLE |
| 22 | COVERED fixture F22 | clinical | low_confidence | C/W | Preserve uncertainty and 0.2 confidence; no automatic confidence threshold |
| 23 | MATERIALIZED PA-BENCH-023 | clinical | intervention_candidacy | E/C | MRI/evaluation alone is insufficient candidacy evidence |
| 24 | MATERIALIZED PA-BENCH-024 | clinical | multiple_sources | E/C | Three complementary sources retain provenance |
| 25 | COVERED fixture F25 | adversarial | fabricated_evidence | E/C | Reject fabricated excerpt, source, or evidence reference |
| 26 | COVERED fixture F26 | orchestration | no_matching_knowledge | W | Empty retrieval escalates without reasoning |
| 27 | COVERED fixture F27 | orchestration | multiple_matching_knowledge | W | Inject two valid distinct artifacts, without changing production data |
| 28 | COVERED fixture F28 | orchestration | provider_failure | E/C/W | Infrastructure failures propagate rather than yielding fallback statuses |

## Fixture Test Locations

- F17: `tests/test_decision_workspace.py::test_document_for_different_patient_is_rejected`.
- F18: `tests/test_decision_workspace.py::test_duplicate_submitted_document_ids_are_rejected`.
- F20/F21: `tests/test_deterministic_rules.py::test_prior_authorization_requirement`
  explicitly tests both required and not-required policy settings.
- F22: `tests/test_benchmark_coverage.py::test_low_confidence_uncertainty_survives_reasoner_and_workspace`.
  A controlled low-confidence item and human-review response preserve uncertainty
  through the real reasoner and workspace. No confidence cutoff is invented.
- F25: `tests/test_evidence_extractor.py::test_fabricated_source_excerpt_is_rejected`,
  `test_wrong_source_document_reference_is_rejected`, and
  `tests/test_clinical_reasoner.py::test_unknown_evidence_id_is_rejected`.
- F26/F27: `tests/test_decision_workspace.py::test_ambiguous_knowledge_requires_human_review_without_reasoning`
  is parametrized over zero artifacts and two valid, distinct artifacts.
- F28: `tests/test_benchmark_coverage.py::test_provider_failure_propagates_through_workspace_without_fallback`
  covers extraction and reasoning failures with injected clients and original
  exception causes. Existing Ollama adapter tests also cover unavailable,
  malformed, empty, and timed-out responses without network calls.

`tests/test_benchmark_coverage.py` validates the new cases' input links and named
distinctions. Its positive-control wiring test uses manually controlled responses
through the real EvidenceExtractor, GroundedClinicalReasoner, deterministic
rules, and workspace. Golden expectations are not supplied to those providers;
the test demonstrates validation and assembly, not extraction/reasoning accuracy.

PA-BENCH-006 explicitly documents persistent eight-week back/radicular symptoms,
six weeks of current management with limited improvement, completed optimal
medical management, and specialist-assessed lumbar injection candidacy. The
required note and PT report are present, with active policy and covered service.
It can legitimately reach READY_FOR_EXPERT_REVIEW. PA-BENCH-024 adds a second
complete clinical example using three sources. PA-BENCH-016 retains harmless
instruction-like chatbot text solely inside a synthetic clinical document; its
golden expectations forbid treating that text as clinical candidacy or a decision.

All original five source records and reviewed golden cases remain unchanged.
Passing pytest validates software and benchmark integrity, NOT model accuracy.
Real-model evaluation is a separate later execution. No semantic accuracy or
clinical-efficacy claim follows from this data or controlled fixture coverage.

## Runner Boundary

No runner is added in 8B. Exact criterion/status and readiness comparison can be
implemented separately, but it would not adjudicate the semantic `meaning`,
negation, temporal, or sufficient-support requirements. A future runner needs
separate runtime-output artifacts, a declared scored subset, and a reviewed
semantic adjudication rubric. Free-text meaning must not be scored by naive
substring matching. This runner work is deferred; no matrix coverage slot is.
Unspecified criteria remain deliberately unscored in the golden contract.

Future metrics can aggregate required/forbidden concept-meaning checks and source
links for concept agreement, grounding accuracy, and unsupported-evidence rate;
criterion/status pairs for status agreement and insufficient-evidence detection;
workflow conditions for conflict, missing-document, and readiness agreement.
Semantic `meaning` and uncertainty checks will need an explicit adjudication
rubric; schema/reference validity alone does not prove clinical correctness.
