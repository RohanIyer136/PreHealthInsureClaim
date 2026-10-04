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
from backend.repositories.demo_workspaces import (
    DemoArtifact, DemoWorkspaceRepository, source_fingerprint, validate_source,
)
from backend.repositories.synthetic_cases import (
    CaseNotFoundError, CaseRepositoryError, SyntheticCaseRepository,
)
from backend.services.decision_workspace import DecisionWorkspaceError

def select_authorization_ids(repository, requested=None):
    """Use repository authority and validate all requested IDs before inference."""
    identifiers = list(dict.fromkeys(requested)) if requested else [
        case.authorization_id for case in repository.list_cases()
    ]
    for identifier in identifiers:
        repository.get_case(identifier)
    return identifiers


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--authorization-id", action="append", help="Generate one case; repeat for a subset")
    selection.add_argument("--missing-only", action="store_true", help="Generate only cases lacking validated artifacts")
    selection.add_argument("--check-coverage", action="store_true", help="Check coverage offline; exit 1 if incomplete")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    repository = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    directory = ROOT / "demo/workspaces"
    if args.check_coverage or args.missing_only:
        demos = DemoWorkspaceRepository(directory, repository)
        identifiers = demos.missing_authorization_ids()
        print(f"{len(repository.list_cases())} source cases; {len(identifiers)} missing valid artifacts", flush=True)
        if args.check_coverage:
            for identifier in identifiers:
                print(identifier)
            return 1 if identifiers else 0
    else:
        identifiers = select_authorization_ids(repository, args.authorization_id)
    if not identifiers:
        print("No cases need generation.", flush=True)
        return 0
    service = build_local_workspace_service(timeout=args.timeout)
    for index, identifier in enumerate(identifiers, 1):
        print(f"[{index}/{len(identifiers)}] Generating {identifier} through production local orchestration...", flush=True)
        generate(identifier, repository, service, ROOT / "demo/workspaces",
                 model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EvidenceExtractionError, ClinicalReasoningError, DecisionWorkspaceError,
            CaseNotFoundError, CaseRepositoryError, ValidationError, OSError, ValueError) as exc:
        print(f"Demo generation failed ({type(exc).__name__}); "
              "no artifact was written for the failing case. See sanitized diagnostics.",
              file=sys.stderr)
        sys.exit(1)
