# PreHealthInsureClaim

Local API (synthetic source data only):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health`: liveness, no workflow or AI execution.
- `GET /api/v1/cases`: sorted source summaries.
- `GET /api/v1/cases/{authorization_id}`: patient, policy, authorization, submitted documents.
- `POST /api/v1/cases/{authorization_id}/analyze`: existing workspace orchestration.

Interactive API documentation: `http://127.0.0.1:8000/docs`.
Only analysis invokes local Ollama; it can take several minutes. Defaults remain
`OLLAMA_BASE_URL=http://localhost:11434` and `OLLAMA_MODEL=qwen3:8b`. No API key.
Document requirements come from the existing fictional insurance policy artifact,
not benchmark expectations. Domain rules, validation, and readiness derivation are unchanged.

### Execution Routing

The production builder configures `IMG-MRI-LS` for existing lumbar clinical
retrieval and reasoning. The deterministic router uses exact service-code
configuration, never document keywords or model-selected tools. Existing policy
and document checks run first. Explicit routing control marks failed coverage
validity and service-coverage rules terminal, skipping AI. Other deficiencies,
including missing documentation, may continue useful clinical preparation while
remaining authoritative in workspace readiness. Required knowledge is checked before inference.
An `EXECUTION_PLANNED` audit event records the typed plan and reasons.

Unconfigured services or unavailable required clinical/insurance capabilities
require expert review without invented clinical criteria. Insurance reasoning and
benefit utilization are declared future capabilities, not implemented engines.
Lumbar PT documentation requirements apply only to the configured lumbar service.
Other document requirements need deliberate future configuration.
The existing case repository now serves 55 synthetic cases: the original 19 plus
36 source-only runtime cases described in [synthetic_data/RUNTIME_CASES.md](synthetic_data/RUNTIME_CASES.md).
Administrative-only processing and unavailable clinical capabilities are explicitly
recorded in workspaces; only the existing lumbar service enables clinical AI.

`DecisionWorkspaceService(execution_router=...)` enables this routing; the production
builder always supplies it. Existing injected setups without a router retain their
original full-pipeline behavior. No final authorization decision is generated.
`HUMAN_REVIEW` in a plan means exceptional escalation, not the normal final expert
decision. Successful preparation plans omit that capability; every workspace still
requires a human expert for the final authorization decision.
Design-only multidomain specifications are not runtime configuration; their separate
source-only runtime copies contain no evaluation targets. Frozen demo
workspaces remain historical saved outputs, not regenerated routed outputs.

`CORS_ORIGINS` is a comma-separated allowlist, defaulting to
`http://localhost:5173,http://127.0.0.1:5173`. Credentials are disabled.
`create_app(repository=..., workspace_service=...)` and the dependency functions
in `backend/api/dependencies.py` provide offline injection points. Nothing under
`evaluation/` is loaded by the API.

Errors use `{"error": {"code": "...", "message": "..."}}`: unknown cases 404,
invalid parameters/workflow inputs 422, rejected AI output 502, local AI failure
503, and internal/source-data failures 500. Public messages never include exception
causes, provider output, or filesystem paths. No approval/rejection endpoints exist.

## Review Interface

Keep the backend command above running. In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL (normally `http://127.0.0.1:5173`). `VITE_API_BASE_URL`
defaults to `http://127.0.0.1:8000`; set it in `frontend/.env.local` for another
local API URL. If Vite chooses another port, add that origin to backend
`CORS_ORIGINS`. Analysis can take several minutes; queue and document browsing
do not invoke Ollama. Final authorization remains with the human reviewer.

Offline frontend checks: `npm test`, `npm run typecheck`, `npm run build`.
The frontend tests mock HTTP and require neither FastAPI nor Ollama.

## Pre-Evaluated Demo Mode

See [demo/README.md](demo/README.md) for selected synthetic cases, artifact
generation, and exact local run commands. `VITE_WORKSPACE_MODE=demo` selects
separate offline demo endpoints; the default `live` mode keeps the existing local
Ollama pipeline. Demo Mode is visibly disclosed and never pretends to run live
inference. Both modes use the same human-review workspace contract.
