"""Tests hors ligne de l'initialisation Google Calendar."""

from types import SimpleNamespace

from integrations.google import calendar


def configurer_calendriers(monkeypatch):
    monkeypatch.setenv("CALENDAR_ID_AMINATA", "agenda_aminata")
    monkeypatch.setenv("CALENDAR_ID_MOUSSA", "agenda_moussa")
    monkeypatch.setenv("CALENDAR_ID_KHADY", "agenda_khady")


def test_configuration_calendriers(monkeypatch):
    configurer_calendriers(monkeypatch)

    resultat = calendar._charger_calendriers()

    assert resultat == {
        "aminata": "agenda_aminata",
        "moussa": "agenda_moussa",
        "khady": "agenda_khady",
    }


def test_configuration_calendrier_manquant(monkeypatch):
    monkeypatch.setenv("CALENDAR_ID_AMINATA", "agenda_aminata")
    monkeypatch.setenv("CALENDAR_ID_MOUSSA", "")
    monkeypatch.setenv("CALENDAR_ID_KHADY", "agenda_khady")

    resultat = calendar._charger_calendriers()

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"
    assert "moussa" in resultat["message"]


def test_connexion_google_calendar(monkeypatch):
    configurer_calendriers(monkeypatch)

    identifiants = SimpleNamespace(nom="identifiants_test")
    service = SimpleNamespace(nom="service_test")
    appels = {}

    def faux_obtenir_identifiants(scopes):
        appels["scopes"] = scopes
        return identifiants

    def faux_build(*args, **kwargs):
        appels["build"] = (args, kwargs)
        return service

    monkeypatch.setattr(
        calendar, "obtenir_identifiants", faux_obtenir_identifiants
    )
    monkeypatch.setattr(calendar, "build", faux_build)

    agenda = calendar.AgendaGoogle.connecter()

    assert isinstance(agenda, calendar.AgendaGoogle)
    assert agenda._service is service
    assert agenda._calendriers["aminata"] == "agenda_aminata"
    assert appels["scopes"] == calendar.SCOPES_CALENDAR
    assert appels["build"][0] == ("calendar", "v3")
    assert appels["build"][1]["credentials"] is identifiants
    assert appels["build"][1]["cache_discovery"] is False


def test_connexion_refusee_si_calendrier_manquant(monkeypatch):
    monkeypatch.setenv("CALENDAR_ID_AMINATA", "")
    monkeypatch.setenv("CALENDAR_ID_MOUSSA", "agenda_moussa")
    monkeypatch.setenv("CALENDAR_ID_KHADY", "agenda_khady")

    def oauth_non_attendu(scopes):
        raise AssertionError("L'OAuth ne doit pas être appelé.")

    monkeypatch.setattr(
        calendar, "obtenir_identifiants", oauth_non_attendu
    )

    resultat = calendar.AgendaGoogle.connecter()

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_erreur_authentification_transmise(monkeypatch):
    configurer_calendriers(monkeypatch)

    resultat_attendu = {
        "ok": False,
        "code": "AUTORISATION",
        "message": "Authentification refusée.",
    }

    monkeypatch.setattr(
        calendar,
        "obtenir_identifiants",
        lambda scopes: resultat_attendu,
    )

    resultat = calendar.AgendaGoogle.connecter()

    assert resultat == resultat_attendu


def test_erreur_initialisation_service(monkeypatch):
    configurer_calendriers(monkeypatch)

    monkeypatch.setattr(
        calendar,
        "obtenir_identifiants",
        lambda scopes: SimpleNamespace(),
    )

    def faux_build(*args, **kwargs):
        raise ConnectionError("connexion impossible")

    monkeypatch.setattr(calendar, "build", faux_build)

    resultat = calendar.AgendaGoogle.connecter()

    assert resultat["ok"] is False
    assert resultat["code"] == "INDISPONIBLE"
    assert "ConnectionError" in resultat["message"]
