"""Validated, pre-evaluated synthetic workspaces; no inference at read time."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.schemas import DecisionWorkspace
from backend.repositories.synthetic_cases import (
    CaseNotFoundError, CaseRepositoryError, CaseSource, SyntheticCaseRepository,
)


def source_fingerprint(case: CaseSource) -> str:
    data = {
        "authorization": case.authorization.model_dump(mode="json"),
        "patient": case.patient.model_dump(mode="json"),
        "policy": case.policy.model_dump(mode="json"),
        "documents": [item.model_dump(mode="json") for item in case.documents],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _reject_unknown_fields(raw: object, validated: object) -> None:
    # Domain models ignore extras by default; artifact storage must not retain them.
    if isinstance(raw, dict) and isinstance(validated, dict):
        if raw.keys() - validated.keys():
            raise ValueError("Unknown workspace artifact fields")
        for key, value in raw.items():
            _reject_unknown_fields(value, validated[key])
    elif isinstance(raw, list) and isinstance(validated, list):
        for value, item in zip(raw, validated):
            _reject_unknown_fields(value, item)


class DemoArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    mode: Literal["pre_evaluated_synthetic_demo"] = "pre_evaluated_synthetic_demo"
    generator: Literal["production_local_ollama"] = "production_local_ollama"
    model: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    workspace: DecisionWorkspace

    @model_validator(mode="before")
    @classmethod
    def validate_stored_workspace(cls, data):
        if isinstance(data, dict) and isinstance(data.get("workspace"), dict):
            raw = data["workspace"]
            workspace = DecisionWorkspace.model_validate(raw)
            _reject_unknown_fields(raw, workspace.model_dump(mode="json"))
        return data


def validate_source(artifact: DemoArtifact, case: CaseSource) -> None:
    if artifact.workspace.authorization_id != case.authorization.authorization_id:
        raise ValueError("Demo authorization identity mismatch")
    if artifact.source_sha256 != source_fingerprint(case):
        raise ValueError("Demo source records have changed; regenerate the artifact")
    documents = {item.document_id: item for item in case.documents}
    for result in artifact.workspace.clinical_results:
        for item in result.evidence:
            document = documents.get(item.source_document_id)
            if document is None or not item.excerpt or item.excerpt not in document.content:
                raise ValueError("Demo clinical citation is not grounded in submitted sources")


class DemoWorkspaceRepository:
    def __init__(self, directory: Path, sources: SyntheticCaseRepository):
        self.directory = directory
        self.sources = sources

    def load(self) -> dict[str, DemoArtifact]:
        artifacts = {}
        try:
            if not self.directory.is_dir():
                raise ValueError("Demo artifacts are unavailable")
            for path in sorted(self.directory.glob("*.json")):
                artifact = DemoArtifact.model_validate_json(path.read_text(encoding="utf-8"))
                identifier = artifact.workspace.authorization_id
                if identifier in artifacts:
                    raise ValueError("Duplicate demo authorization")
                validate_source(artifact, self.sources.get_case(identifier))
                artifacts[identifier] = artifact
        except (OSError, ValueError, CaseNotFoundError) as exc:
            raise CaseRepositoryError("Demo artifacts could not be validated.") from exc
        return artifacts

    def get(self, authorization_id: str) -> DemoArtifact:
        artifacts = self.load()
        if authorization_id not in artifacts:
            raise CaseNotFoundError("Synthetic demo case not found.")
        return artifacts[authorization_id]

    def missing_authorization_ids(self) -> list[str]:
        """Check full source coverage offline; invalid artifacts still fail closed."""
        artifacts = self.load()
        return sorted({case.authorization_id for case in self.sources.list_cases()} - artifacts.keys())
