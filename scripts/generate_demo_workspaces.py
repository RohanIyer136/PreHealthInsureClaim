"""Explicit real local inference: generate validated synthetic demo artifacts."""

import argparse
import os
from pathlib import Path
import sys
from time import perf_counter

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api.dependencies import build_local_workspace_service
from backend.ai.clinical_reasoner import ClinicalReasoningError
from backend.ai.evidence_extractor import EvidenceExtractionError
from backend.models.schemas import DecisionWorkspace
from backend.repositories.demo_workspaces import DemoArtifact, source_fingerprint, validate_source
from backend.repositories.synthetic_cases import CaseRepositoryError, SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceError

DEMO_CASES = ("PA-BENCH-006", "PA-DEMO-002", "PA-DEMO-003")


def generate(authorization_id, repository, service, directory, *, model):
    case = repository.get_case(authorization_id)
    started = perf_counter()
    workspace = service.build(case.authorization, case.patient, case.policy, case.documents)
    workspace = DecisionWorkspace.model_validate(workspace.model_dump(mode="json"))
    artifact = DemoArtifact(
        model=model, source_sha256=source_fingerprint(case),
        elapsed_seconds=perf_counter() - started, workspace=workspace,
    )
    artifact = DemoArtifact.model_validate_json(artifact.model_dump_json())
    validate_source(artifact, case)
    # All validation precedes writing; atomically replace only a completed artifact.
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{authorization_id}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(f"{authorization_id}: {workspace.readiness_status.value}; "
          f"{artifact.elapsed_seconds:.2f}s; validated artifact written", flush=True)
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-id", choices=DEMO_CASES, action="append")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    repository = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    service = build_local_workspace_service(timeout=args.timeout)
    for identifier in args.authorization_id or DEMO_CASES:
        print(f"Generating {identifier} through production local Ollama...", flush=True)
        generate(identifier, repository, service, ROOT / "demo/workspaces",
                 model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"))


if __name__ == "__main__":
    try:
        main()
    except (EvidenceExtractionError, ClinicalReasoningError, DecisionWorkspaceError,
            CaseRepositoryError, ValidationError, OSError, ValueError) as exc:
        print(f"Demo generation failed ({type(exc).__name__}); "
              "no artifact was written for the failing case. See sanitized diagnostics.",
              file=sys.stderr)
        sys.exit(1)
