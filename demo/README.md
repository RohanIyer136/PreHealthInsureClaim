# Pre-Evaluated Synthetic Demo

`workspaces/` contains actual validated production outputs, not clinical answer
keys. Generation runs the same deterministic rules, retrieval, grounded evidence
extraction, and clinical reasoning used by live analysis. Only generation needs
local Ollama. Serving artifacts never invokes a model.

Currently checked-in cases (full repository coverage awaits local generation):

- PA-BENCH-006: explicit complete clinical evidence; expert-review readiness.
- PA-DEMO-002: missing submitted physiotherapy documentation; evidence required.
- PA-DEMO-003: expired policy at submission; human review required.

Generate every case listed by the production `SyntheticCaseRepository` from the
repository root (local qwen3:8b must be available). This includes legacy,
benchmark, and runtime cases; there is no separate demo allowlist:

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_workspaces.py --timeout 300
```

For one case, add `--authorization-id PA-BENCH-006` (repeat the option for a
subset). Unknown IDs fail before service construction. To check coverage offline
without constructing the local inference service:

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_workspaces.py --check-coverage
```

The check lists missing IDs and exits 1 for incomplete coverage (0 when complete).
Malformed, duplicate, stale, or ungrounded artifacts fail closed rather than
being treated as absent. To resume sequentially, generating only missing cases
and retaining the existing valid artifacts:

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_workspaces.py --missing-only --timeout 300
```

These selection options are mutually exclusive. Generation prints progress,
case ID, readiness, and elapsed time. A failing case stops generation visibly;
already completed artifacts remain valid. Every artifact is written only after production workspace validation and
source-grounding checks. Failed runs do not overwrite completed artifacts.
Generation does not force any readiness or clinical status. Model outputs may
vary; inspect the generated artifacts before presenting them.
The generator uses production orchestration without service-specific decisions:
administrative and unsupported pathways may legitimately return no clinical
criteria; unsupported capability preserves human escalation. Supported clinical
pathways use the configured local model. Offline tests never run full Qwen
generation. The full-coverage test is staged as an expected failure while cases
are missing and automatically becomes a passing subset check after generation.
Schema and source-grounding validation do not certify clinical correctness.
The saved PA-DEMO-002 run marked optimal management satisfied using medication
evidence alone, and both PA-DEMO-002 and PA-DEMO-003 marked intervention candidacy
satisfied from MRI-request evidence alone. PA-DEMO-003 also marked optimal
management not satisfied based on limited symptom relief. These are unsupported
clinical inferences requiring reviewer scrutiny. They are preserved as generated,
not edited into benchmark answers. The missing physiotherapy document still
makes PA-DEMO-002 evidence-required; the expired policy makes PA-DEMO-003
human-review-required. These artifacts illustrate workflow behavior and current
model limitations, not clinically certified decisions.

Each envelope records the model, elapsed generation time, generator, schema
version, and SHA-256 of submitted source records. The workspace retains its
original generation timestamp, evidence, source rule IDs, and audit events.
Changed source records fail artifact validation until regeneration. Generation
metadata is not a claim of clinical efficacy or regulatory validation. No model
thinking is stored. These artifacts are synthetic human-review material, never
authorization approval or rejection.

Demo endpoints use `/api/v1/demo/cases` and return the same case/workspace
contracts as live endpoints. Successful responses include
`X-Workspace-Mode: pre-evaluated-synthetic-demo`. Only cases with validated
artifacts appear in this queue. Missing demo cases return 404; malformed or stale
artifacts fail closed with a safe 500 response. There is no live fallback.

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell terminal:

```powershell
cd frontend
$env:VITE_WORKSPACE_MODE = "demo"
npm run dev
```

Open `http://127.0.0.1:5173`. Set `VITE_WORKSPACE_MODE=live` and restart Vite to
return to live local inference. The environment variable is compiled into Vite
builds, so set it before `npm run build` for a demo build. Keep API base URL and
CORS settings aligned if using other ports. No deployment is part of this demo.
Live Local Mode remains separate: FastAPI invokes production orchestration and
local Ollama/Qwen where configured. Public Demo Mode reads only validated,
checked-in, pre-evaluated synthetic workspaces and performs no live inference.
