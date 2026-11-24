"""LangSmith en option : rien n'est instrumenté sans LANGSMITH_TRACING et une clé."""

import anthropic
import pytest

from agent import observabilite


@pytest.mark.parametrize("tracing, cle", [("", ""), ("true", ""), ("false", "lsv2-x")])
def test_inactif_le_client_est_inchange(monkeypatch, tracing, cle):
    monkeypatch.setenv("LANGSMITH_TRACING", tracing)
    monkeypatch.setenv("LANGSMITH_API_KEY", cle)
    client = anthropic.Anthropic(api_key="faux")
    assert observabilite.instrumenter(client) is client and not observabilite.langsmith_actif()


def test_actif_le_client_est_instrumente(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-x")
    vus = []
    monkeypatch.setattr("langsmith.wrappers.wrap_anthropic", lambda c: vus.append(c) or "tracé")
    client = anthropic.Anthropic(api_key="faux")
    assert observabilite.instrumenter(client) == "tracé" and vus == [client]
