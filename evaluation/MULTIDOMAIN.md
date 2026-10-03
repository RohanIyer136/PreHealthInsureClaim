# Multi-Domain Synthetic Benchmark Design

This is a design/data foundation, not new production clinical coverage or a
clinical validation study. No real patient data, proprietary insurance text,
external API, or model output is used. All 36 patients/scenarios are invented;
the lumbar positive note is adapted from existing project-authored synthetic data.
Fictional products are not real insurance contracts, medical guidelines, legal
requirements, or reimbursement promises.

## Scope and Support

The existing lumbar MRI vertical is the only implemented clinical vertical.
Existing PA-* authorizations remain executable by the current application;
the three frozen demo artifacts remain byte-for-byte unchanged.

**All 36 new specifications are DESIGN_ONLY.** ORTH-01 and ORTH-02 reference the
existing lumbar capability and analogous existing cases, not executable aliases.
ORTH-02 deliberately shares the complete ORTH-01 clinical note to isolate document
removal; it is not a copy of the canonical PA-DEMO-002 note or its frozen output.
The other 34 scenarios require future authoritative clinical knowledge artifacts,
service mappings, and deliberate implementation. Nothing routes them through
Qwen or the API. Breadth of this matrix must not be advertised as clinical coverage.

Even the two lumbar specifications use new fictional products that are not wired
to production insurance rules. Therefore overall readiness is unscored (null) for
all 36. Only the two lumbar controls carry clinical statuses backed by
ACR-LBP-VARIANT-3 and explicit source assertions. Missing the PT report in ORTH-02
must not erase the common note's clinical assertions; documentation completeness
and clinical interpretation are independent layers.

## Files and Contracts

- Inputs: `synthetic_data/benchmark_design/cases.json`.
- Products: `synthetic_data/benchmark_design/policies.json`.
- Golden specifications and comparisons: `evaluation/multidomain_cases.json`.
- Strict validation and reference checks: `evaluation/multidomain.py`.
- Offline integrity/isolation tests: `tests/test_multidomain_benchmark.py`.

The input files contain scenario facts, demographics, requested services, source
documents, policy assignment/utilization, and design metadata. Intentional omissions
are test-design metadata, not inferred clinical conclusions. Source content is
untrusted data, including copied instructions and patient statements. Names,
addresses, dates of birth, contact details, and real patient identifiers are absent.

Golden targets are physically separate. They must never be included in model
context or API case payloads. A future materializer must supply only appropriate
clinical documents and authorized policy facts, not tags, omissions metadata,
comparisons, expected findings, or scoring labels. Existing backend loaders read
only their four existing files; they do not discover this nested design directory.
Backend modules may not import evaluation modules. Frontend code is unchanged.

Contracts reuse existing strict Pydantic conventions and existing document, sex,
criterion-status, and readiness enums. Additional urgency, document-role, benefit,
and design-evidence taxonomies are local to the evaluation specification, not
extensions to production domain schemas or extractor concepts. Document roles
separate pathology from biomarkers even when both have type LAB_RESULT.

## Families

- ORTH: Orthopedics / Trauma; six named scenarios.
- SURG: Surgery / GI; six named scenarios.
- ONC: Oncology; six named scenarios.
- ACUTE: Cardiology / Neurology / Critical Care; six named scenarios.
- MED: Medical / Infectious / Chronic; six named scenarios.
- SPEC: Special Benefits / Rehabilitation / Maternity; six named scenarios.

## Fictional Products

Every product has a version, effective interval, network characteristics,
explicit administrative prior-authorization categories, separate emergency
handling, ten structured benefit categories, exclusions, limits, documentation
roles, and synthetic/project-authored disclaimers.

| Product | Design purpose |
|---|---|
| P1_ESSENTIAL | Restricted basic outpatient/emergency coverage; six rehab visits; elective surgery, specialty medication, maternity, and dental not included |
| P2_STANDARD | Standard network, imaging/elective surgery; twelve rehab visits; lumbar-example PT documentation requirement |
| P3_PREMIUM | Extended network and specialty-treatment review; twenty-four rehab visits; imaging ordinary authorization not required |
| P4_FAMILY_PLUS | Maternity and routine dental visits; sixteen rehab visits; specialty medication not included |
| P5_CHRONIC_CARE | Chronic-care programs and specialty medication; eighteen rehab visits; twelve-month recurring-program limit |
| P6_RESTRICTED_LEGACY | Restricted legacy version 0.9; four rehab visits; specialty medication excluded; active through 2027-12-31 |

Other products are version 1.0; all products are effective 2025-01-01 through
2027-12-31. Case service dates are fixed at 2026-10-02 except MED-05, which uses
2028-01-02 with supporting documents dated 2028-01-01. Dates are not evaluated
against the developer's current wall clock. MED-05 isolates expiry of P5's
otherwise-included chronic-care benefit. Limits apply only where a benefit is included.
Purely cosmetic intent and elective dental implants are excluded in all products;
reconstructive intent must remain distinct from cosmetic intent. Category handling
is illustrative: new service-specific medical eligibility rules are not defined.
The lumbar PT requirement is scoped to the lumbar example, not all imaging.
Emergency timing is fictional expedited/retrospective administrative review,
never permission to delay care or infer coverage, payment, or legal compliance.

## Controlled Comparisons

- ORTH-01 / ORTH-02 (missing_document): Remove only physiotherapy source; preserve all explicit clinical assertions in the common note. Missing documentation changes, not the interpretation of unchanged facts.
- SURG-02 / SURG-03 (missing_document): Remove only diagnostic ultrasound; detect the missing source without inventing surgical eligibility.
- ONC-04 / ONC-05 (missing_document): Remove only a project-defined supporting marker form; never fabricate marker results.
- SPEC-01 / SPEC-02 (utilization): Keep request, policy, and clinical documentation constant; change only recorded visits used across the fictional benefit limit.
- ONC-03 / ONC-06 (policy): Keep every clinical input constant and switch only active policy product. Clinical interpretation remains stable; coverage and administrative findings change without an effective-date conflict.

Validation enforces unchanged demographics, service, urgency, severity, and
service date. Document-removal pairs remove exactly one otherwise unchanged
source and keep policy/utilization fixed. Policy and utilization pairs preserve
identical clinical documents, including source IDs; shared IDs across paired cases
are intentional. SPEC-01 uses four prior visits plus six requested visits (10/12);
SPEC-02 uses twelve prior visits plus the same six requested (18/12).
ONC-03 versus ONC-06 changes one input variable, policy product. Both products are
active for the unchanged shared service date of 2026-10-02; only coverage and
administrative handling differ. Expired-policy detection is tested independently
by MED-05, whose chronic-care benefit is included but whose service date is after
P5's effective interval.

## Robustness and Negative Controls

Six scenarios have explicit challenges:

- ORTH-03: conflicting neurological observations in separate sources.
- ORTH-05: copied instruction-like intake text stays untrusted document data.
- ORTH-06: patient-reported insurer approval is not authoritative authorization.
- MED-05: an otherwise-included policy benefit is requested after policy expiry.
- MED-01: unrelated historical information must not become current support.
- MED-06: a specialty-treatment request cannot establish missing eligibility facts.

Routine negative controls are ORTH-04, MED-01, and MED-02. They must not manufacture
an invasive/surgical authorization problem. Emergency/time-critical scenarios
are ORTH-03, SURG-01, ACUTE-01, ACUTE-04, ACUTE-06, and SPEC-04. Urgent requests
remain distinct from both routine requests and emergency exceptions. Urgency alone
is not evidence of coverage or clinical eligibility. Future urgent-versus-elective
workflow evaluation must use explicit, reviewed service-specific rules.

## Matrix

All rows are design-only. Document counts refer only to submitted sources;
missing sources are not made available for citations.

| Case | Scenario / request | Policy | Urgency | Docs | Control / challenge |
|---|---|---|---|---|---|
| ORTH-01 | Lumbar MRI without contrast for persistent radiculopathy | P2_STANDARD | routine | 2 | positive_control |
| ORTH-02 | Lumbar MRI without contrast for persistent radiculopathy | P2_STANDARD | routine | 1 | missing physiotherapy |
| ORTH-03 | Emergency ORIF for displaced tibial fracture after vehicle accident | P2_STANDARD | emergency | 3 | cross_document_contradiction |
| ORTH-04 | Conservative outpatient care for stable wrist fracture | P1_ESSENTIAL | routine | 2 | negative_control |
| ORTH-05 | Elective total knee replacement for severe knee osteoarthritis | P3_PREMIUM | routine | 3 | prompt_injection |
| ORTH-06 | Reconstructive facial-fracture surgery after assault | P4_FAMILY_PLUS | urgent | 2 | reported_approval |
| SURG-01 | Emergency appendectomy for acute appendicitis | P1_ESSENTIAL | emergency | 2 | design baseline |
| SURG-02 | Elective laparoscopic cholecystectomy for symptomatic gallstones | P2_STANDARD | routine | 2 | design baseline |
| SURG-03 | Elective laparoscopic cholecystectomy for symptomatic gallstones | P2_STANDARD | routine | 1 | missing diagnostic_imaging |
| SURG-04 | Elective repair of reducible inguinal hernia | P2_STANDARD | routine | 2 | design baseline |
| SURG-05 | Urgent endoscopy for acute gastrointestinal bleeding | P3_PREMIUM | urgent | 2 | design baseline |
| SURG-06 | Purely cosmetic rhinoplasty | P2_STANDARD | routine | 1 | design baseline |
| ONC-01 | Diagnostic biopsy of suspicious breast mass | P2_STANDARD | routine | 2 | design baseline |
| ONC-02 | Surgical treatment of localized breast malignancy | P3_PREMIUM | routine | 3 | design baseline |
| ONC-03 | Synthetic systemic treatment for confirmed colorectal malignancy | P3_PREMIUM | routine | 3 | design baseline |
| ONC-04 | Synthetic high-cost treatment for metastatic lung malignancy | P3_PREMIUM | routine | 4 | design baseline |
| ONC-05 | Synthetic high-cost treatment for metastatic lung malignancy | P3_PREMIUM | routine | 3 | missing biomarker |
| ONC-06 | Synthetic systemic treatment for confirmed colorectal malignancy | P6_RESTRICTED_LEGACY | routine | 3 | active-policy coverage comparison |
| ACUTE-01 | Emergency PCI pathway for acute STEMI-type presentation | P3_PREMIUM | emergency | 2 | design baseline |
| ACUTE-02 | Elective coronary angiography for stable coronary disease | P2_STANDARD | routine | 2 | design baseline |
| ACUTE-03 | Pacemaker/device request for symptomatic bradyarrhythmia | P3_PREMIUM | urgent | 2 | design baseline |
| ACUTE-04 | Time-sensitive intervention for acute ischemic stroke | P2_STANDARD | time_critical | 2 | design baseline |
| ACUTE-05 | Higher-acuity admission for diabetic ketoacidosis | P5_CHRONIC_CARE | urgent | 3 | design baseline |
| ACUTE-06 | Emergency ICU admission for septic shock | P1_ESSENTIAL | emergency | 2 | design baseline |
| MED-01 | Routine outpatient care for uncomplicated influenza-like illness | P1_ESSENTIAL | routine | 2 | irrelevant_information; negative_control |
| MED-02 | Routine outpatient care for uncomplicated viral URI and cough | P4_FAMILY_PLUS | routine | 1 | negative_control |
| MED-03 | Inpatient admission for community-acquired pneumonia | P2_STANDARD | urgent | 3 | design baseline |
| MED-04 | Higher-acuity admission for severe pneumonia with hypoxemia | P3_PREMIUM | urgent | 3 | design baseline |
| MED-05 | Recurring chronic-care program for chronic kidney disease | P5_CHRONIC_CARE | routine | 2 | expired_policy |
| MED-06 | High-cost specialty treatment for multiple sclerosis | P5_CHRONIC_CARE | routine | 1 | unsupported_inference; missing specialist_assessment |
| SPEC-01 | Six-visit post-operative knee physiotherapy course | P2_STANDARD | routine | 2 | design baseline |
| SPEC-02 | Six-visit post-operative knee physiotherapy course | P2_STANDARD | routine | 2 | benefit limit |
| SPEC-03 | Routine antenatal maternity care | P4_FAMILY_PLUS | routine | 1 | design baseline |
| SPEC-04 | Emergency admission and delivery pathway for pregnancy complication | P4_FAMILY_PLUS | emergency | 2 | design baseline |
| SPEC-05 | Cataract surgery for reading-related functional limitation | P3_PREMIUM | routine | 2 | design baseline |
| SPEC-06 | Elective dental implant | P1_ESSENTIAL | routine | 1 | design baseline |

## Evaluation Meaning

Golden specifications separate evidence targets and their legitimate source IDs,
missing information, conflicts, fictional policy facts, emergency/escalation design
targets, and prohibited inferences. Existing clinical expectations reference the
actual lumbar artifact and criterion IDs. Other evidence concepts are design-only
semantic targets; they are not new production extraction enums.

Future-domain records explicitly require future domain knowledge and cannot carry
clinical statuses or readiness labels. Documentation completeness here describes
submitted project-defined forms, not real-world eligibility. Oncology marker X is
fictional: no drug, dose, biomarker threshold, regimen choice, or treatment guideline
is asserted. Level-of-care, device, stroke, trauma, and maternity cases likewise
contain no invented medical eligibility thresholds.

No exact generated evidence IDs or natural-language outputs are required. Semantic
meaning, negation, episode timing, sufficient support, and cross-source conflicts
will require a reviewed adjudication rubric. Passing integrity tests is not model
accuracy, clinical efficacy, regulatory validation, or production domain coverage.
No runner, scoring implementation, new database, retrieval infrastructure, model
provider, or production capability is introduced here.

## Offline Validation

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests validate all contracts and references, controlled comparisons, demographic
and scenario variation, knowledge limitations, closed enums, policy dates/limits,
API isolation, and pinned SHA-256 hashes for all three frozen demo files. No Ollama
or network call is needed. Existing lumbar, API, and demo tests remain unchanged.
