# Intelligence Map

`intelligence_map.json` is a planning manifest for exactly the 36 DESIGN_ONLY
inputs, not runtime configuration, a new golden answer file, or a medical efficacy
claim. `intelligence_map.py` validates it against input/service metadata and the
six fictional products only. No golden specifications are read. No case becomes
executable merely by appearing here.

## Scope and Categories

Every entry names its family and requested service. Shared deterministic checks
are policy dates/eligibility, category coverage, prior-authorization requirement,
and document completeness. Per-entry flags add visit utilization, structured
exclusions, and emergency administrative handling. Missing-document relevance
marks a scenario's focus, not whether other cases should skip completeness checks.
Clinical AI requires the existing extraction/retrieval/grounded reasoning pipeline.
HUMAN_REVIEW remains exceptional escalation support, not a predicted outcome or
the ordinary final expert decision. Complexity estimates implementation effort for
the stated scope only; LOW emergency administration does not mean low clinical risk.

The three primary groups partition the matrix. Controls/emergencies overlap them.

| Group | Count | Cases |
|---|---:|---|
| Deterministic-dominant | 15 | ORTH-04; SURG-01,06; ONC-06; ACUTE-01,04,06; MED-01,02,05; SPEC-01,02,03,04,06 |
| Clinical-AI-dominant | 13 | ORTH-01; SURG-02,04; ONC-01,02,03,04; ACUTE-02,03,05; MED-03,04; SPEC-05 |
| Combined | 8 | ORTH-02,03,05,06; SURG-03,05; ONC-05; MED-06 |
| Negative controls | 3 | ORTH-04; MED-01,02 |
| Emergency/time-critical | 6 | ORTH-03; SURG-01; ACUTE-01,04,06; SPEC-04 |

Clinical-dominant still runs all shared administrative checks. Combined highlights
additional documentation, adversarial provenance, urgent coordination, exclusion
intent, or conflicting/temporally changing evidence, not a different AI engine.
SURG-05 is urgent, not structured emergency; urgency must not be reclassified from
keywords. ORTH-03's examinations differ over time: do not automatically call that
a contradiction or invent a neurological diagnosis.

## Reusable Capabilities

- One structured eligibility/coverage/prior-authorization evaluator across all six
  products; no insurance LLM for explicit flags, dates, or category membership.
- One service-scoped document-role completeness capability across all 36. Four
  missing-source focuses: ORTH-02, SURG-03, ONC-05, MED-06. Marker and pathology
  share LAB_RESULT, so type alone cannot distinguish their roles. Service-specific
  requirements need explicit configuration; the broad product rule is insufficient
  for the surgical imaging and fictional marker-form controls.
- One utilization capability for SPEC-01/02, using explicit ledger arithmetic and
  benefit-period context. No clinical inference from visit counts. Other units and
  periods require actual utilization data, absent from the expired MED-05 branch.
- One structured exclusion capability: SURG-06, ONC-06, SPEC-06; plus reconstructive
  versus cosmetic handling in ORTH-06. Do not treat reported approval as policy truth.
- One emergency administrative capability for all six emergency/time-critical
  cases, driven by urgency and policy timing. It must never determine treatment
  eligibility, care priority, legal compliance, or whether care should be delayed.
- One grounded clinical pipeline, with service-scoped retrieved criteria rather
  than case-specific engines; shared literal grounding and untrusted-text protection.
- One exceptional escalation mechanism for absent knowledge, source uncertainty,
  conflicting findings, or unsupported capabilities. Final authorization is human.

## Knowledge and Executability

**17 cases can be prepared without new clinical knowledge after future metadata,
policy, document-role, and service wiring:** the 15 deterministic-dominant entries
above plus ORTH-01/02, which reuse ACR-LBP-VARIANT-3. They are not executable now.
Routine/emergency/utilization/exclusion entries are administrative demonstrations,
not claims that fracture care, surgery, rehab, maternity, stroke, or ICU necessity
has been clinically evaluated. MED-01 extraction robustness may be evaluated
separately offline; it is not a reason to invoke AI in routine administration.
ONC-03/06 share clinical inputs; ONC-06's map scope is coverage-only. Skipping
clinical preparation there must not fabricate a different clinical conclusion.

For clinical preparation of the other **19** entries, the minimum planning
portfolio is **seven new knowledge families**, alongside existing lumbar imaging:

| New family | Cases | Distinct scope needed within the family |
|---|---|---|
| Musculoskeletal procedures | ORTH-03,05,06 | Trauma fixation, knee arthroplasty, facial reconstruction |
| General surgery / GI | SURG-02,03,04,05 | Cholecystectomy, hernia repair, GI bleeding/endoscopy and care setting |
| Oncology | ONC-01,02,03,04,05 | Breast diagnostics/surgery; treatment-specific systemic therapy |
| Cardiology | ACUTE-02,03 | Angiography and device indications are separate scopes |
| Acute level of care | ACUTE-05; MED-03,04 | DKA and pneumonia-specific admission/acuity criteria |
| Neurology specialty | MED-06 | Service-specific MS treatment assessment |
| Ophthalmology | SPEC-05 | Cataract functional/appropriateness criteria |

These are reusable sourcing/maintenance families, **not seven universal medical
rules or a promise that seven artifacts suffice**. Neither a generic diagnosis
presence check nor the lumbar imaging artifact can substitute for them. Existing
knowledge schema is imaging-shaped and extractor concepts are lumbar-oriented;
future non-imaging support needs a deliberate contract extension, not stuffed fields.
Unnamed ONC-03/04/05 treatments, fictional marker X, and unspecified MED-06 treatment
prevent genuine treatment-specific eligibility evaluation until service definitions
and authoritative scope are supplied. Missing thresholds/data stay missing.

**Zero new knowledge families are needed for an honest administrative-only breadth
demo plus the existing lumbar vertical.** Supporting clinical necessity for all 36
would require additional emergency, outpatient, obstetric, rehabilitation, etc.
scopes beyond this deliberately limited map; that is not a credible speed-run goal.

## Suggested Order

1. 14B: structured product eligibility/coverage/intent and prior-authorization checks.
2. Add service-scoped document-role completeness and visit utilization.
3. Add fictional emergency administrative timing, without waiting for AI or gating care.
4. Materialize appropriate source-only service metadata, wire capabilities explicitly,
   and preserve lumbar behavior. Never promote this planning file into runtime inputs.
5. Extend non-imaging contracts deliberately, then add one sourced clinical scope
   and regression tests at a time; cholecystectomy shares SURG-02/03, and pneumonia
   shares MED-03/04. Leave underspecified treatments and other domains safely unsupported.
