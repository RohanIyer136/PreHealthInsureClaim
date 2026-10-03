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
not benchmark expectations. Domain rules, validation, and readiness are unchanged.

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
