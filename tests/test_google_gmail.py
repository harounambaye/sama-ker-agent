"""Tests hors ligne de l'integration Google Gmail."""

import base64
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
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


class FauxRequete:
    def __init__(self, resultat):
        self.resultat = resultat

    def execute(self):
        if isinstance(self.resultat, Exception):
            raise self.resultat
        return self.resultat


class FauxLabels:
    def __init__(self, libelles):
        self.libelles = libelles

    def list(self, **kwargs):
        return FauxRequete({"labels": self.libelles})


class FauxMessages:
    def __init__(self, pages, messages):
        self.pages = pages
        self.messages = messages
        self.appels_pages = []

    def list(self, **kwargs):
        self.appels_pages.append(kwargs)
        token = kwargs.get("pageToken")
        return FauxRequete(self.pages[token])

    def get(self, **kwargs):
        return FauxRequete(self.messages[kwargs["id"]])


class FauxThreads:
    def __init__(self, fils):
        self.fils = fils
        self.appels = []

    def get(self, **kwargs):
        self.appels.append(kwargs)
        return FauxRequete(self.fils[kwargs["id"]])


class FauxDrafts:
    def __init__(self):
        self.corps = None
        self.appels_envoi = []
        self.resultat_envoi = {"id": "message-envoye"}

    def create(self, **kwargs):
        self.corps = kwargs
        return FauxRequete({"id": "brouillon-1"})

    def send(self, **kwargs):
        self.appels_envoi.append(kwargs)
        return FauxRequete(self.resultat_envoi)


class FauxUsers:
    def __init__(self, libelles, pages, messages, fils=None):
        self._labels = FauxLabels(libelles)
        self._messages = FauxMessages(pages, messages)
        self._threads = FauxThreads(fils or {})
        self._drafts = FauxDrafts()

    def labels(self):
        return self._labels

    def messages(self):
        return self._messages

    def threads(self):
        return self._threads

    def drafts(self):
        return self._drafts


class FauxServiceGmail:
    def __init__(self, libelles, pages, messages, fils=None):
        self._users = FauxUsers(libelles, pages, messages, fils)

    def users(self):
        return self._users


def encoder_base64(texte):
    return base64.urlsafe_b64encode(
        texte.encode("utf-8")
    ).decode("ascii").rstrip("=")


def creer_message(message_id, fil_id, corps, date_ms):
    return {
        "id": message_id,
        "threadId": fil_id,
        "internalDate": str(date_ms),
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Client <client@example.com>"},
                {"name": "Subject", "value": "Demande de visite"},
            ],
            "body": {"data": encoder_base64(corps)},
        },
    }


def test_lire_demandes_sans_libelle():
    service = FauxServiceGmail(
        libelles=[],
        pages={},
        messages={},
    )

    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.lire_demandes()

    assert resultat == {"ok": True, "demandes": []}


def test_lire_demandes_message_simple():
    date_ms = int(
        datetime(2026, 11, 18, 10, 30, tzinfo=timezone.utc).timestamp()
        * 1000
    )

    message = creer_message(
        "message-1",
        "fil-1",
        "Bonjour, je cherche un appartement.",
        date_ms,
    )

    service = FauxServiceGmail(
        libelles=[
            {"id": "label-1", "name": "SamaKer/A traiter"}
        ],
        pages={
            None: {"messages": [{"id": "message-1"}]}
        },
        messages={"message-1": message},
    )

    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.lire_demandes()

    assert resultat["ok"] is True
    assert len(resultat["demandes"]) == 1

    demande = resultat["demandes"][0]

    assert demande["message_id"] == "message-1"
    assert demande["fil_id"] == "fil-1"
    assert demande["expediteur"] == "Client <client@example.com>"
    assert demande["sujet"] == "Demande de visite"
    assert demande["corps"] == "Bonjour, je cherche un appartement."
    assert demande["recu_le"] == "2026-11-18T10:30:00+00:00"


def test_lire_demandes_pagination():
    premier = creer_message("message-1", "fil-1", "Premier", 1795000000000)
    second = creer_message("message-2", "fil-2", "Second", 1795000000000)

    service = FauxServiceGmail(
        libelles=[
            {"id": "label-1", "name": "SamaKer/A traiter"}
        ],
        pages={
            None: {
                "messages": [{"id": "message-1"}],
                "nextPageToken": "page-2",
            },
            "page-2": {
                "messages": [{"id": "message-2"}],
            },
        },
        messages={
            "message-1": premier,
            "message-2": second,
        },
    )

    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.lire_demandes()

    assert resultat["ok"] is True
    assert len(resultat["demandes"]) == 2
    assert resultat["demandes"][0]["corps"] == "Premier"
    assert resultat["demandes"][1]["corps"] == "Second"

    appels = service._users._messages.appels_pages
    assert len(appels) == 2
    assert appels[0]["labelIds"] == ["label-1"]
    assert appels[1]["pageToken"] == "page-2"


def test_lire_demandes_erreur_autorisation():
    class FauxErreurAPI(Exception):
        resp = type("Reponse", (), {"status": 403})()

    service = FauxServiceGmail(
        libelles=[],
        pages={},
        messages={},
    )
    service._users._labels.list = lambda **kwargs: FauxRequete(
        FauxErreurAPI()
    )

    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.lire_demandes()

    assert resultat["ok"] is False
    assert resultat["code"] == "AUTORISATION"


def test_lire_demandes_multipart_privilegie_texte_brut():
    message = creer_message("message-1", "fil-1", "", 1795000000000)

    message["payload"] = {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Client <client@example.com>"},
            {"name": "Subject", "value": "Demande"},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": encoder_base64("Texte brut du message")},
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": encoder_base64("<p>Version HTML</p>")
                },
            },
        ],
    }

    service = FauxServiceGmail(
        libelles=[
            {"id": "label-1", "name": "SamaKer/A traiter"}
        ],
        pages={None: {"messages": [{"id": "message-1"}]}},
        messages={"message-1": message},
    )

    resultat = gmail.MessagerieGoogle(service).lire_demandes()

    assert resultat["ok"] is True
    assert resultat["demandes"][0]["corps"] == "Texte brut du message"


def test_lire_demandes_repli_sur_html():
    message = creer_message("message-1", "fil-1", "", 1795000000000)

    message["payload"] = {
        "mimeType": "text/html",
        "headers": [],
        "body": {
            "data": encoder_base64(
                "<html><body><p>Bonjour</p><p>Je cherche un logement.</p></body></html>"
            )
        },
    }

    service = FauxServiceGmail(
        libelles=[
            {"id": "label-1", "name": "SamaKer/A traiter"}
        ],
        pages={None: {"messages": [{"id": "message-1"}]}},
        messages={"message-1": message},
    )

    resultat = gmail.MessagerieGoogle(service).lire_demandes()

    assert resultat["ok"] is True
    assert resultat["demandes"][0]["corps"] == (
        "Bonjour Je cherche un logement."
    )


def test_lire_demandes_ignore_piece_jointe():
    message = creer_message("message-1", "fil-1", "", 1795000000000)

    message["payload"] = {
        "mimeType": "multipart/mixed",
        "headers": [],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": encoder_base64("Corps du message")},
            },
            {
                "mimeType": "text/plain",
                "filename": "document.txt",
                "body": {
                    "data": encoder_base64("Contenu de la piece jointe")
                },
            },
        ],
    }

    service = FauxServiceGmail(
        libelles=[
            {"id": "label-1", "name": "SamaKer/A traiter"}
        ],
        pages={None: {"messages": [{"id": "message-1"}]}},
        messages={"message-1": message},
    )

    resultat = gmail.MessagerieGoogle(service).lire_demandes()

    assert resultat["ok"] is True
    assert resultat["demandes"][0]["corps"] == "Corps du message"

def test_creer_brouillon_dans_fil_existant():
    ancien = creer_message(
        "message-ancien",
        "fil-1",
        "Premier message",
        1795000000000,
    )

    dernier = creer_message(
        "message-dernier",
        "fil-1",
        "Dernier message",
        1795000000000,
    )

    dernier["payload"]["headers"].extend([
        {"name": "Message-ID", "value": "<dernier@example.com>"},
        {
            "name": "References",
            "value": "<premier@example.com>",
        },
    ])

    service = FauxServiceGmail(
        libelles=[],
        pages={},
        messages={},
        fils={
            "fil-1": {
                "messages": [ancien, dernier],
            }
        },
    )

    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.creer_brouillon(
        "fil-1",
        "Bonjour, votre demande a bien ete recue.",
    )

    assert resultat == {
        "ok": True,
        "brouillon_id": "brouillon-1",
    }

    appel = service._users._threads.appels[0]
    assert appel["id"] == "fil-1"
    assert appel["format"] == "full"

    corps = service._users._drafts.corps["body"]
    assert corps["message"]["threadId"] == "fil-1"

    donnees = corps["message"]["raw"]
    donnees += "=" * (-len(donnees) % 4)

    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(donnees)
    )

    assert message["To"] == "Client <client@example.com>"
    assert message["Subject"] == "Re: Demande de visite"
    assert message["In-Reply-To"] == "<dernier@example.com>"
    assert message["References"] == (
        "<premier@example.com> <dernier@example.com>"
    )
    assert message.get_content().strip() == (
        "Bonjour, votre demande a bien ete recue."
    )


def test_creer_brouillon_conserve_sujet_re_existant():
    dernier = creer_message(
        "message-1",
        "fil-1",
        "Message",
        1795000000000,
    )
    dernier["payload"]["headers"].append({
        "name": "Subject",
        "value": "Re: Demande de visite",
    })

    service = FauxServiceGmail(
        libelles=[],
        pages={},
        messages={},
        fils={"fil-1": {"messages": [dernier]}},
    )

    resultat = gmail.MessagerieGoogle(service).creer_brouillon(
        "fil-1",
        "Ma reponse",
    )

    assert resultat["ok"] is True

    donnees = service._users._drafts.corps["body"]["message"]["raw"]
    donnees += "=" * (-len(donnees) % 4)

    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(donnees)
    )

    assert message["Subject"] == "Re: Demande de visite"


def test_creer_brouillon_arguments_invalides():
    service = FauxServiceGmail([], {}, {})
    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.creer_brouillon(" ", "Une reponse")

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_creer_brouillon_fil_vide():
    service = FauxServiceGmail(
        libelles=[],
        pages={},
        messages={},
        fils={"fil-1": {"messages": []}},
    )

    resultat = gmail.MessagerieGoogle(service).creer_brouillon(
        "fil-1",
        "Une reponse",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"


def test_envoyer_brouillon_avec_succes():
    service = FauxServiceGmail([], {}, {})
    messagerie = gmail.MessagerieGoogle(service)

    resultat = messagerie.envoyer_brouillon("brouillon-1")

    assert resultat == {"ok": True}
    assert service._users._drafts.appels_envoi == [
        {
            "userId": "me",
            "body": {"id": "brouillon-1"},
        }
    ]


def test_envoyer_brouillon_identifiant_invalide():
    service = FauxServiceGmail([], {}, {})
    messagerie = gmail.MessagerieGoogle(service)

    for brouillon_id in ("", "   ", None, 123):
        resultat = messagerie.envoyer_brouillon(brouillon_id)

        assert resultat["ok"] is False
        assert resultat["code"] == "ARGUMENT_INVALIDE"

    assert service._users._drafts.appels_envoi == []


def test_envoyer_brouillon_introuvable():
    service = FauxServiceGmail([], {}, {})
    erreur_api = RuntimeError("Brouillon absent")
    erreur_api.resp = SimpleNamespace(status=404)
    service._users._drafts.resultat_envoi = erreur_api

    resultat = gmail.MessagerieGoogle(service).envoyer_brouillon(
        "brouillon-inexistant"
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
