# Synthetic Authorization Benchmark

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
rules. A genuinely complete explicit-candidacy positive control is planned below.
Cases 002-005 keep their original readiness; absent candidacy is explicitly
represented without masking missing documents, policy expiry, ambiguity, or conflict.

## Planned Matrix

28 slots total: 5 materialized, 23 deferred. Planning IDs are not authorization
IDs. E = extraction, C = clinical reasoning, W = workflow/deterministic behavior.
`synthetic` means a future source case; `fixture` means a focused offline
unit/integration scenario, not a fabricated patient record. Rows describe planned
behaviors, not claimed measured performance.

| Slot | State / Source | Category | Tags | Layers | Named behavior |
|---|---|---|---|---|---|
| 01 | Existing PA-DEMO-001 | clinical | complete_documents, cross_document_evidence, intervention_candidacy | E/C/W | Complete documents do not prove candidacy |
| 02 | Existing PA-DEMO-002 | orchestration | missing_required_document | E/W | Unsubmitted physiotherapy report cannot be used |
| 03 | Existing PA-DEMO-003 | insurance | expired_policy | W | Expiry at submission blocks routine readiness |
| 04 | Existing PA-DEMO-004 | clinical | ambiguous_wording, missing_clinical_evidence | E/C/W | Preserve materially ambiguous duration |
| 05 | Existing PA-DEMO-005 | clinical | cross_document_contradiction, conflicting_treatment_duration | E/C/W | Conflicting treatment histories require review |
| 06 | Planned synthetic | clinical | complete_documents, explicit_candidacy | E/C/W | Explicit sufficient evidence for every criterion; positive control |
| 07 | Planned synthetic | clinical | missing_clinical_evidence | E/C/W | No treatment history yields insufficient evidence |
| 08 | Planned synthetic | clinical | explicit_contrary_evidence | E/C | Explicit non-candidacy supports NOT_SATISFIED |
| 09 | Planned synthetic | clinical | approximate_duration | E/C | Approximation must survive extraction and reasoning |
| 10 | Planned synthetic | clinical | negation | E/C | Negated symptoms must not become positive findings |
| 11 | Planned synthetic | clinical | historical_treatment | E/C | Previous episode treatment is not current management |
| 12 | Planned synthetic | clinical | temporal_confusion | E/C | Distinguish symptom onset, treatment start, document dates |
| 13 | Planned synthetic | clinical | cross_document_evidence | E/C | Complementary documents jointly support a criterion |
| 14 | Planned synthetic | clinical | cross_document_contradiction | E/C/W | Conflicting neurological findings remain independent |
| 15 | Planned synthetic | clinical | irrelevant_information | E/C | Unrelated facts do not support target criteria |
| 16 | Planned synthetic | adversarial | prompt_injection | E/C | Clinical instruction-like text stays data |
| 17 | Planned fixture | orchestration | wrong_patient | W | Reject wrong-patient source before AI execution |
| 18 | Planned fixture | orchestration | duplicate_document | W | Reject duplicate submitted document IDs |
| 19 | Planned synthetic | insurance | uncovered_service | W | Uncovered service category is a deterministic blocker |
| 20 | Planned fixture | insurance | prior_authorization | W | Required prior authorization is recorded without deciding approval |
| 21 | Planned fixture | insurance | prior_authorization | W | Not-required prior authorization uses existing deterministic behavior |
| 22 | Planned fixture | clinical | low_confidence | C/W | Preserve uncertain evidence; no invented confidence threshold |
| 23 | Planned synthetic | clinical | intervention_candidacy | E/C | MRI/evaluation alone is insufficient candidacy evidence |
| 24 | Planned synthetic | clinical | multiple_sources | E/C | Three complementary sources retain provenance |
| 25 | Planned fixture | adversarial | fabricated_evidence | E/C | Reject fabricated excerpt, source, or evidence reference |
| 26 | Planned fixture | orchestration | no_matching_knowledge | W | Empty retrieval escalates; reasoning is not invoked |
| 27 | Planned fixture | orchestration | multiple_matching_knowledge | W | Inject two valid distinct artifacts; no production-data corruption |
| 28 | Planned fixture | orchestration | provider_failure | E/C/W | Infrastructure failures propagate, never become insufficient evidence |

8A implements only the materialized authorization contract and integrity checks.
Fixture input/error contracts, new source cases, runtime result formats, scoring,
and runners are deferred. In particular, fixture rows must not be shoehorned into
`golden_cases.json` with nonexistent authorization IDs. Review ambiguous/optimal
management adjudications when expanding expectations; unspecified criteria are
deliberately unscored.

Future metrics can aggregate required/forbidden concept-meaning checks and source
links for concept agreement, grounding accuracy, and unsupported-evidence rate;
criterion/status pairs for status agreement and insufficient-evidence detection;
workflow conditions for conflict, missing-document, and readiness agreement.
Semantic `meaning` and uncertainty checks will need an explicit adjudication
rubric; schema/reference validity alone does not prove clinical correctness.
