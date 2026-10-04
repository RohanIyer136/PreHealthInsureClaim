# PreHealthInsureClaim

## Healthcare Decision Workspace

Healthcare Decision Workspace is a working prototype for **AI-assisted healthcare prior authorization**.

Prior authorization decisions often require reviewers to bring together insurance coverage rules, required documentation, clinical evidence, and exceptions before a decision can be made.

This prototype turns that fragmented process into a single **evidence-backed decision workspace**.

> **The system does not automate the final authorization decision. It prepares the decision context for a human reviewer.**

---

## 🚀 Live Prototype

### [Open the Healthcare Decision Workspace](https://pre-health-insure-claim.vercel.app/)

The public prototype contains **55 synthetic authorization cases** covering different services, policies, documentation states, and processing pathways.

The deployment runs in **Demo Mode** using validated, pre-evaluated synthetic cases so it can be demonstrated without exposing a live AI inference service.

**No real patient data is used.**

### Recommended Cases

For a quick walkthrough, try these three cases:

| Case | Scenario | Demonstrates |
|---|---|---|
| `PA-BENCH-006` | MRI Lumbar Spine | ✅ **Ready for Expert Review** — clinical criteria are supported by source-linked evidence |
| `PA-MD-ORTH-02` | Lumbar MRI with incomplete documentation | ⚠️ **Evidence Required** — identifies missing physiotherapy documentation |
| `PA-MD-ONC-03` | Oncology systemic treatment | 🛡️ **Human Review Required** — safely escalates an unsupported clinical capability instead of guessing |

### How to Explore

1. Open the prototype.
2. Search for one of the case IDs above.
3. Review **Case & documents**.
4. Select **Analyze Authorization**.
5. Inspect the **Decision workspace**.

The workspace shows insurance and documentation findings, missing information, clinical criteria where supported, source-linked evidence, escalation reasons, and the processing trace.

---

## 💡 Design Principle

Not every authorization problem requires AI.

The system separates work into three broad paths:

- **Deterministic processing** — explicit coverage, policy, documentation, benefit, and administrative rules.
- **Clinical AI processing** — unstructured clinical evidence is evaluated against configured clinical criteria.
- **Human escalation** — unsupported or uncertain cases are escalated rather than forcing an automated conclusion.

> **We don't automate clinical judgment. We automate everything surrounding clinical judgment.**

---

## 🧠 How It Works

```text
      Authorization Request
               │
               ▼
    Policy + Documents + Case
               │
               ▼
      Deterministic Checks
               │
               ▼
        Execution Router
          ┌────┴────┐
          │         │
          ▼         ▼
 Administrative   Clinical AI
    Pathway        Pathway
                      │
                      ▼
              Knowledge Retrieval
                      │
                      ▼
              Evidence Extraction
                      │
                      ▼
              Criterion Reasoning
                      │
                      ▼
            Grounding & Validation
          └───────────┬───────────┘
                      ▼
              Decision Workspace
                      │
                      ▼
                Human Reviewer
```

Explicit rules are handled deterministically. AI is used selectively where interpretation of unstructured clinical evidence adds value.

The final authorization decision always remains with the human reviewer.

---

## 🏗️ Technical Architecture

| Layer | Implementation |
|---|---|
| Frontend | React + TypeScript + Vite |
| API | FastAPI |
| Data contracts | Pydantic |
| Decision logic | Python deterministic evaluation services |
| Orchestration | Typed execution router + Decision Workspace service |
| Clinical knowledge | Versioned structured knowledge artifacts |
| Retrieval | Exact service/scope-based retrieval |
| LLM | Qwen3:8B |
| Local inference | Ollama |
| Public frontend | Vercel |
| Public backend | Render |

### Execution Routing

The execution router determines which capabilities a case requires before clinical inference occurs.

Policy and documentation checks run first. Explicit terminal findings can prevent unnecessary AI execution, while missing documentation can still allow useful clinical preparation when appropriate.

Currently configured clinical AI pathways include:

- `IMG-MRI-LS` — lumbar spine MRI
- `SURG-CHOLECYSTECTOMY` — laparoscopic cholecystectomy

Unsupported clinical services are explicitly escalated to human review without generating invented clinical criteria.

---

## 🤖 AI Grounding & Safety

For supported clinical cases, the local AI pipeline performs:

1. Clinical knowledge retrieval
2. Evidence extraction from submitted documents
3. Criterion-level clinical reasoning
4. Source/citation grounding
5. Structured output validation

Model output is treated as **untrusted until validated**.

If clinical reasoning output fails validation, the system permits one bounded structured-output repair using the same evidence and knowledge. The repaired result must pass the same validator; otherwise the pipeline fails closed.

The LLM does **not** determine final authorization.

The current local implementation uses:

```text
Qwen3:8B
    ↓
Ollama
    ↓
Structured clinical output
    ↓
Deterministic validation
    ↓
Decision Workspace
```

This design also keeps the model provider replaceable rather than coupling the workflow to a specific hosted AI API.

---

## 🎭 Public Demo vs Local Live Mode

| Capability | Public Demo | Local Live |
|---|:---:|:---:|
| Synthetic cases | ✅ | ✅ |
| Decision workspace | ✅ | ✅ |
| Insurance/document findings | ✅ | ✅ |
| Clinical evidence & criteria | ✅ Pre-evaluated | ✅ Live |
| Human escalation | ✅ | ✅ |
| Live Qwen inference | ❌ | ✅ |
| Ollama required | ❌ | ✅ |
| Real patient data | ❌ | ❌ |

The public deployment serves validated frozen workspace artifacts.

The local system runs the full supported workflow, including Qwen inference through Ollama.

---

## 💻 Running Locally

### Backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Main endpoints:

```text
GET  /health
GET  /api/v1/cases
GET  /api/v1/cases/{authorization_id}
POST /api/v1/cases/{authorization_id}/analyze
```

Live clinical analysis requires Ollama. Defaults:

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

No API key is required.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend normally runs at:

```text
http://127.0.0.1:5173
```

---

## 🔐 Runtime Modes

The backend supports two explicit runtime modes:

```text
APP_MODE=full
APP_MODE=demo
```

### `full`

Used for local development.

Provides the live authorization workflow, Demo Mode APIs, deterministic evaluation, and supported local AI inference.

### `demo`

Used by the public deployment.

Only the frozen Demo Mode APIs are registered. Live workflow routes are unavailable and the live Ollama/Qwen service is not constructed.

This makes the public deployment boundary **server-side rather than only a frontend setting**.

---

## 🧪 Prototype Data & Evaluation

The repository contains **55 synthetic runtime authorization cases** spanning multiple healthcare service families and decision pathways.

Cases exercise behaviors including:

- complete authorization submissions
- missing required documentation
- policy and coverage checks
- administrative-only processing
- supported clinical evaluation
- unsupported clinical capabilities
- human escalation
- adversarial and conflicting inputs

Synthetic policies and clinical documentation are used throughout the prototype.

Automated tests cover the API, domain models, deterministic rules, routing, AI contracts and validation, demo artifact integrity, runtime modes, and frontend behavior.

---

## ⚠️ Prototype Scope

This project is a technical prototype built with **synthetic patient data, fictional insurance policies, and synthetic authorization requests**.

It demonstrates decision-workflow orchestration, deterministic insurance processing, selective AI-assisted clinical analysis, evidence grounding, safe escalation, and human-in-the-loop decision support.

It is **not** a medical device, production insurer system, or autonomous authorization engine.

Clinical knowledge represented in the prototype is intentionally limited and versioned. Production use would require formal clinical, regulatory, privacy, security, and customer-specific policy validation.

---

## Core Principle

**AI prepares the decision. Humans remain responsible for making it.**
