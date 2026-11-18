"""Tests hors ligne de l'integration Google Gmail."""

from types import SimpleNamespace

from integrations.google import gmail


def test_connexion_google_gmail(monkeypatch):
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
        gmail,
        "obtenir_identifiants",
        faux_obtenir_identifiants,
    )
    monkeypatch.setattr(gmail, "build", faux_build)

    messagerie = gmail.MessagerieGoogle.connecter()

    assert isinstance(messagerie, gmail.MessagerieGoogle)
    assert messagerie._service is service
    assert appels["scopes"] == gmail.SCOPES_GMAIL
    assert appels["build"][0] == ("gmail", "v1")
    assert appels["build"][1]["credentials"] is identifiants
    assert appels["build"][1]["cache_discovery"] is False


def test_scope_gmail_modify():
    assert gmail.SCOPES_GMAIL == [
        "https://www.googleapis.com/auth/gmail.modify",
    ]


def test_erreur_authentification_transmise(monkeypatch):
    resultat_attendu = {
        "ok": False,
        "code": "AUTORISATION",
        "message": "Authentification refusee.",
    }

    monkeypatch.setattr(
        gmail,
        "obtenir_identifiants",
        lambda scopes: resultat_attendu,
    )

    resultat = gmail.MessagerieGoogle.connecter()

    assert resultat == resultat_attendu


def test_erreur_initialisation_service(monkeypatch):
    monkeypatch.setattr(
        gmail,
        "obtenir_identifiants",
        lambda scopes: SimpleNamespace(),
    )

    def faux_build(*args, **kwargs):
        raise RuntimeError("erreur de test")

    monkeypatch.setattr(gmail, "build", faux_build)

    resultat = gmail.MessagerieGoogle.connecter()

    assert resultat["ok"] is False
    assert resultat["code"] == "INDISPONIBLE"
    assert "RuntimeError" in resultat["message"]
