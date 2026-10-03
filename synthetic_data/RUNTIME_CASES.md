# Multi-Domain Runtime Source Records

`runtime_cases.json` adds 36 project-authored synthetic prototype cases to the
existing 19 records, for 55 cases through the existing SyntheticCaseRepository and
`/api/v1/cases` endpoints. Authorization IDs are PA-MD-ORTH-01 through
PA-MD-SPEC-06. The original four source files and three frozen demo artifacts are
unchanged. No new medical guidance, patient information, or insurer commitments
are represented.

The checked-in file is a source-only snapshot: patient demographics, policy/product
bindings, authorizations, clinical documents, document roles, service dates, intent,
urgency, and utilization. Source clinical text, document types, dates, and roles are
preserved from the design inputs. Design tags, omissions labels, scenario purposes,
complexity classifications, expected results, and scoring are not promoted. Runtime
does not discover or read the design directory, evaluation data, or planning map.
Parity checks read both sources in offline tests only; there is no generation system
or runtime dependency on design inputs. Future source edits need explicit review.

Policies bind to the six fictional templates in
`backend/runtime/synthetic_insurance.json` using explicit member/policy IDs.
The member identifiers are invented synthetic source identifiers, not claims of
independent membership verification. Requests/documents use case-specific IDs to
avoid patient-reference collisions in the original design pairs. Cross-policy pairs
preserve demographics, requested service, urgency, service date, document roles and
clinical text, but use distinct patient/member/policy record IDs because the existing
Patient contract binds one policy context. They are controlled clinical-fact copies,
not a demonstration of real member policy switching.

**Explicit runtime ledger addition:** SPEC-01/02 retain their source visit counts
(4 or 12 used, 6 requested), with a project-authored 2026-01-01 to 2026-12-31 ledger
period, visits units and a 12-month period. The original design did not contain a
dated ledger. These are declared new synthetic administrative facts, not inferred
from clinical prose or fabricated defaults in the evaluator. Other missing utilization
stays missing and requires review when applicable.

Thirty explicit service configurations cover all 36 cases. Routine respiratory
controls share one service code; clinical-name differences remain on requests. The
router uses service codes and insurance findings, never authorization IDs:

- 15 administrative scenarios: ORTH-04; SURG-01,06; ONC-06; ACUTE-01,04,06;
  MED-01,02,05; SPEC-01,02,03,04,06. No clinical AI. Workspaces explicitly record
  ADMINISTRATIVE_PREPARATION_ONLY; readiness is not medical-necessity validation.
- ORTH-01/02 reuse IMG-MRI-LS and ACR-LBP-VARIANT-3. Clinical extraction/reasoning
  runs only after applicable terminal checks and knowledge preflight. Missing PT
  remains non-terminal, visible in missing evidence while useful interpretation continues.
- The other 19 services require unavailable clinical knowledge. Insurance checks
  run, then human escalation occurs without retrieval, extraction or reasoning.
  No lumbar fallback or generic medical reasoning is enabled.
- ONC-03/06 share a service configuration. The excluded-policy branch is terminal;
  the included-policy branch safely reports unavailable clinical capability.
- Emergency/time-critical requests preserve structured urgency in insurance_context.
  Existing ROUTINE/URGENT priority is a coarser queue display; emergency administration
  does not select treatment or permission to delay care.

Existing endpoint and queue shapes are retained. The queue displays service names
and source specialty descriptions; category is available in requested_service.
Detail responses include fictional product terms and structured insurance context.
No new pages, endpoints, frontend redesign, or autonomous final decisions are added.
Frozen Demo Mode continues serving only its original three saved workspaces.
