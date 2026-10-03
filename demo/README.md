# Pre-Evaluated Synthetic Demo

`workspaces/` contains actual validated production outputs, not clinical answer
keys. Generation runs the same deterministic rules, retrieval, grounded evidence
extraction, and clinical reasoning used by live analysis. Only generation needs
local Ollama. Serving artifacts never invokes a model.

Selected cases:

- PA-BENCH-006: explicit complete clinical evidence; expert-review readiness.
- PA-DEMO-002: missing submitted physiotherapy documentation; evidence required.
- PA-DEMO-003: expired policy at submission; human review required.

Regenerate from the repository root (local qwen3:8b must be available):

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_workspaces.py --timeout 300
```

For one case, add `--authorization-id PA-BENCH-006` (repeat the option for a
subset). Every artifact is written only after production workspace validation and
source-grounding checks. Failed runs do not overwrite completed artifacts.
Generation does not force any readiness or clinical status. Model outputs may
vary; inspect the generated artifacts before presenting them.
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
