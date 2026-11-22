"""Vérification du compte Google : sans réseau (faux service Google)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from agent.preparer_google import preparer_libelles, verifier_agendas, verifier_configuration
from contracts import LIBELLES
from integrations.google.calendar import AgendaGoogle


def test_configuration_incomplete_dit_ce_qui_manque(tmp_path):
    problemes = verifier_configuration({"GOOGLE_CREDENTIALS": str(tmp_path / "absent.json"),
                                        "CALENDAR_ID_AMINATA": "a"})
    texte = " ".join(problemes)
    assert "fichier OAuth absent" in texte and "CALENDAR_ID_MOUSSA" in texte
    assert "CALENDAR_ID_AMINATA" not in texte and "AGENCE_EMAIL" in texte and "BRIQUES" in texte


def test_configuration_complete(tmp_path):
    cred = tmp_path / "credentials.json"
    cred.write_text("{}")
    env = {"GOOGLE_CREDENTIALS": str(cred), "AGENCE_EMAIL": "agence@example.com",
           "BRIQUES": "google", "CALENDAR_ID_AMINATA": "a", "CALENDAR_ID_MOUSSA": "m",
           "CALENDAR_ID_KHADY": "k"}
    assert verifier_configuration(env) == []


def test_seuls_les_libelles_manquants_sont_crees():
    svc = MagicMock()
    svc.users().labels().list().execute.return_value = {
        "labels": [{"name": LIBELLES["a_traiter"]}, {"name": "INBOX"}]}
    crees, presents = preparer_libelles(svc)
    assert presents == [LIBELLES["a_traiter"]] and len(crees) == 3
    noms = [c.kwargs["body"]["name"] for c in svc.users().labels().create.call_args_list]
    assert sorted(noms) == sorted(crees)


def test_agendas_verifies_un_par_un():
    svc = MagicMock()
    svc.freebusy().query().execute.return_value = {"calendars": {
        "a": {"busy": []}, "m": {"errors": [{"reason": "notFound"}]}, "k": {"busy": []}}}
    agenda = AgendaGoogle(svc, {"aminata": "a", "moussa": "m", "khady": "k"})
    r = verifier_agendas(agenda, datetime(2026, 11, 23, 8, tzinfo=timezone.utc))
    assert r["aminata"]["ok"] and r["aminata"]["creneaux"]
    assert r["moussa"]["code"] == "INTROUVABLE"
