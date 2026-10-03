"""CLI wiring checks with offline workspace ports only."""

from backend.api import dependencies
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from scripts import smoke_test_ollama
from tests.test_decision_workspace import make_workspace_service
from tests.test_synthetic_case_repository import make_repository


def test_full_case_cli_honors_timeout_and_prints_validated_citations(monkeypatch, capsys):
    calls = []
    service, *_ = make_workspace_service()

    def factory(*, timeout):
        calls.append(timeout)
        return service

    monkeypatch.setattr(dependencies, "build_local_workspace_service", factory)
    monkeypatch.setattr(SyntheticCaseRepository, "from_directory", lambda directory: make_repository())
    monkeypatch.setattr(smoke_test_ollama.sys, "argv", [
        "smoke_test_ollama.py", "--authorization-id", "AUTHORIZATION-17", "--timeout", "300",
    ])
    smoke_test_ollama.main()
    assert calls == [300.0]
    output = capsys.readouterr().out
    assert "Validated cited evidence:" in output
    assert '"excerpt": "Symptoms have persisted for six weeks."' in output
    assert "thinking" not in output
