"""Tests hors ligne de l'intégration Google Calendar."""

from types import SimpleNamespace

import httplib2
from googleapiclient.errors import HttpError

from integrations.google import calendar


def configurer_calendriers(monkeypatch):
    monkeypatch.setenv("CALENDAR_ID_AMINATA", "agenda_aminata")
    monkeypatch.setenv("CALENDAR_ID_MOUSSA", "agenda_moussa")
    monkeypatch.setenv("CALENDAR_ID_KHADY", "agenda_khady")


class FauxService:
    def __init__(self, reponse):
        self.reponse = reponse
        self.corps = None
        self.nombre_reessais = None

    def freebusy(self):
        return self

    def query(self, body):
        self.corps = body
        return self

    def execute(self, num_retries=0):
        self.nombre_reessais = num_retries
        return self.reponse


def creer_agenda(reponse):
    service = FauxService(reponse)
    agenda = calendar.AgendaGoogle(
        service,
        {
            "aminata": "agenda_aminata",
            "moussa": "agenda_moussa",
            "khady": "agenda_khady",
        },
    )
    return agenda, service


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


def test_lister_creneaux_exclut_les_periodes_occupees():
    agenda, service = creer_agenda(
        {
            "calendars": {
                "agenda_aminata": {
                    "busy": [
                        {
                            "start": "2026-11-18T09:00:00Z",
                            "end": "2026-11-18T10:00:00Z",
                        }
                    ]
                }
            }
        }
    )

    resultat = agenda.lister_creneaux_libres(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "2026-11-18T11:00:00+00:00",
    )

    assert resultat["ok"] is True
    assert len(resultat["creneaux"]) == 2
    assert resultat["creneaux"][0]["debut"] == "2026-11-18T10:00:00+00:00"
    assert resultat["creneaux"][0]["fin"] == "2026-11-18T10:45:00+00:00"
    assert resultat["creneaux"][1]["debut"] == "2026-11-18T10:15:00+00:00"
    assert service.nombre_reessais == 2
    assert service.corps["timeZone"] == "Africa/Dakar"
    assert service.corps["items"] == [{"id": "agenda_aminata"}]


def test_lister_creneaux_de_tous_les_conseillers():
    agenda, _ = creer_agenda(
        {
            "calendars": {
                "agenda_aminata": {"busy": []},
                "agenda_moussa": {
                    "busy": [
                        {
                            "start": "2026-11-18T09:00:00Z",
                            "end": "2026-11-18T09:45:00Z",
                        }
                    ]
                },
                "agenda_khady": {"busy": []},
            }
        }
    )

    resultat = agenda.lister_creneaux_libres(
        None,
        "2026-11-18T09:00:00+00:00",
        "2026-11-18T09:45:00+00:00",
    )

    assert resultat["ok"] is True
    assert [c["conseiller"] for c in resultat["creneaux"]] == [
        "aminata",
        "khady",
    ]


def test_lister_creneaux_refuse_les_dates_sans_fuseau():
    agenda, _ = creer_agenda({"calendars": {}})

    resultat = agenda.lister_creneaux_libres(
        "aminata",
        "2026-11-18T09:00:00",
        "2026-11-18T10:00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_lister_creneaux_refuse_un_intervalle_invalide():
    agenda, _ = creer_agenda({"calendars": {}})

    resultat = agenda.lister_creneaux_libres(
        "aminata",
        "2026-11-18T11:00:00+00:00",
        "2026-11-18T09:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_lister_creneaux_refuse_un_conseiller_inconnu():
    agenda, _ = creer_agenda({"calendars": {}})

    resultat = agenda.lister_creneaux_libres(
        "inconnu",
        "2026-11-18T09:00:00+00:00",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_lister_creneaux_exclut_le_dimanche():
    agenda, _ = creer_agenda(
        {"calendars": {"agenda_aminata": {"busy": []}}}
    )

    resultat = agenda.lister_creneaux_libres(
        "aminata",
        "2026-11-22T09:00:00+00:00",
        "2026-11-22T12:00:00+00:00",
    )

    assert resultat == {"ok": True, "creneaux": []}


def test_lister_creneaux_gere_un_agenda_inaccessible():
    agenda, _ = creer_agenda(
        {
            "calendars": {
                "agenda_aminata": {
                    "errors": [{"reason": "forbidden"}]
                }
            }
        }
    )

    resultat = agenda.lister_creneaux_libres(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "AUTORISATION"


class FauxRequeteEvenement:
    def __init__(self, action):
        self.action = action

    def execute(self):
        return self.action()


class FauxEvenements:
    def __init__(
        self,
        evenement=None,
        conflit_insert=False,
        evenement_apres_conflit=None,
    ):
        self.evenement = evenement
        self.conflit_insert = conflit_insert
        self.evenement_apres_conflit = evenement_apres_conflit
        self.corps = None
        self.corps_update = None
        self.nombre_get = 0
        self.nombre_insert = 0
        self.nombre_update = 0

    def get(self, calendarId, eventId):
        self.nombre_get += 1

        def executer():
            if self.evenement is None:
                raise HttpError(
                    httplib2.Response(
                        {"status": "404", "reason": "Not Found"}
                    ),
                    b"not found",
                    uri="https://calendar.googleapis.com/",
                )
            return self.evenement

        return FauxRequeteEvenement(executer)

    def insert(self, calendarId, body):
        self.nombre_insert += 1
        self.corps = body

        def executer():
            self.evenement = body

            if self.conflit_insert:
                if self.evenement_apres_conflit is not None:
                    self.evenement = self.evenement_apres_conflit

                raise HttpError(
                    httplib2.Response(
                        {"status": "409", "reason": "Conflict"}
                    ),
                    b"conflict",
                    uri="https://calendar.googleapis.com/",
                )

            return body

        return FauxRequeteEvenement(executer)

    def update(self, calendarId, eventId, body):
        self.nombre_update += 1
        self.corps_update = body

        def executer():
            self.evenement = body
            return body

        return FauxRequeteEvenement(executer)


class FauxServiceCreation:
    def __init__(
        self,
        evenement=None,
        conflit_insert=False,
        evenement_apres_conflit=None,
    ):
        self.ressource_evenements = FauxEvenements(
            evenement,
            conflit_insert,
            evenement_apres_conflit,
        )

    def events(self):
        return self.ressource_evenements


def creer_agenda_creation(
    evenement=None,
    conflit_insert=False,
    evenement_apres_conflit=None,
):
    service = FauxServiceCreation(
        evenement,
        conflit_insert,
        evenement_apres_conflit,
    )

    agenda = calendar.AgendaGoogle(
        service,
        {
            "aminata": "agenda_aminata",
            "moussa": "agenda_moussa",
            "khady": "agenda_khady",
        },
    )

    agenda.lister_creneaux_libres = (
        lambda conseiller, debut, fin: {
            "ok": True,
            "creneaux": [
                {
                    "conseiller": conseiller,
                    "debut": debut,
                    "fin": fin,
                }
            ],
        }
    )

    return agenda, service

def test_creer_visite_avec_succes():
    agenda, service = creer_agenda_creation()

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, Sénégal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    evenement_id = calendar.id_evenement(
        "fil-123",
        "2026-11-18T09:00:00+00:00",
    )

    assert resultat == {
        "ok": True,
        "evenement_id": evenement_id,
        "deja_existante": False,
    }
    assert service.ressource_evenements.nombre_get == 1
    assert service.ressource_evenements.nombre_insert == 1
    assert service.ressource_evenements.corps["location"] == "Dakar, Sénégal"
    assert service.ressource_evenements.corps["start"]["dateTime"] == (
        "2026-11-18T09:00:00+00:00"
    )
    assert service.ressource_evenements.corps["end"]["dateTime"] == (
        "2026-11-18T09:45:00+00:00"
    )


def test_creer_visite_ne_duplique_pas_un_evenement_existant():
    evenement_id = calendar.id_evenement(
        "fil-123",
        "2026-11-18T09:00:00+00:00",
    )
    agenda, service = creer_agenda_creation({"id": evenement_id})

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, Sénégal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    assert resultat == {
        "ok": True,
        "evenement_id": evenement_id,
        "deja_existante": True,
    }
    assert service.ressource_evenements.nombre_get == 1
    assert service.ressource_evenements.nombre_insert == 0


def test_creer_visite_reactive_un_evenement_annule():
    evenement_id = calendar.id_evenement(
        "fil-123",
        "2026-11-18T09:00:00+00:00",
    )
    evenement_annule = {
        "id": evenement_id,
        "status": "cancelled",
        "summary": "Ancienne visite",
    }

    agenda, service = creer_agenda_creation(evenement_annule)

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, S?n?gal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    assert resultat == {
        "ok": True,
        "evenement_id": evenement_id,
        "deja_existante": False,
    }
    assert service.ressource_evenements.nombre_get == 1
    assert service.ressource_evenements.nombre_insert == 0
    assert service.ressource_evenements.nombre_update == 1
    assert service.ressource_evenements.corps_update["status"] == "confirmed"
    assert service.ressource_evenements.corps_update["start"]["dateTime"] == (
        "2026-11-18T09:00:00+00:00"
    )
    assert service.ressource_evenements.corps_update["end"]["dateTime"] == (
        "2026-11-18T09:45:00+00:00"
    )


def test_creer_visite_reactive_un_evenement_annule_apres_conflit_google():
    evenement_id = calendar.id_evenement(
        "fil-123",
        "2026-11-18T09:00:00+00:00",
    )
    evenement_annule = {
        "id": evenement_id,
        "status": "cancelled",
        "summary": "Ancienne visite",
    }

    agenda, service = creer_agenda_creation(
        conflit_insert=True,
        evenement_apres_conflit=evenement_annule,
    )

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, S?n?gal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    assert resultat == {
        "ok": True,
        "evenement_id": evenement_id,
        "deja_existante": False,
    }
    assert service.ressource_evenements.nombre_get == 2
    assert service.ressource_evenements.nombre_insert == 1
    assert service.ressource_evenements.nombre_update == 1
    assert service.ressource_evenements.corps_update["status"] == "confirmed"


def test_creer_visite_refuse_un_creneau_indisponible():
    agenda, service = creer_agenda_creation()

    agenda.lister_creneaux_libres = (
        lambda conseiller, debut, fin: {
            "ok": True,
            "creneaux": [],
        }
    )

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, Sénégal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "CRENEAU_INDISPONIBLE"
    assert service.ressource_evenements.nombre_insert == 0


def test_creer_visite_refuse_des_arguments_invalides():
    agenda, service = creer_agenda_creation()

    resultat = agenda.creer_visite(
        "aminata",
        "date-invalide",
        "bien-123",
        "Dakar, Sénégal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"
    assert service.ressource_evenements.nombre_get == 0
    assert service.ressource_evenements.nombre_insert == 0

def test_creer_visite_confirme_un_doublon_apres_un_conflit_google():
    agenda, service = creer_agenda_creation(conflit_insert=True)

    resultat = agenda.creer_visite(
        "aminata",
        "2026-11-18T09:00:00+00:00",
        "bien-123",
        "Dakar, Sénégal",
        "Awa Ndiaye",
        "awa@example.com",
        "fil-123",
    )

    evenement_id = calendar.id_evenement(
        "fil-123",
        "2026-11-18T09:00:00+00:00",
    )

    assert resultat == {
        "ok": True,
        "evenement_id": evenement_id,
        "deja_existante": True,
    }
    assert service.ressource_evenements.nombre_get == 2
    assert service.ressource_evenements.nombre_insert == 1

# tests du déplacement de visite

class FauxEvenementsDeplacement:
    def __init__(self, agendas):
        self.agendas = agendas
        self.calendrier_modifie = None
        self.corps_modification = None
        self.nombre_patch = 0

    def get(self, calendarId, eventId):
        def executer():
            evenement = self.agendas.get(calendarId, {}).get(eventId)

            if evenement is None:
                raise HttpError(
                    httplib2.Response({"status": "404", "reason": "Not Found"}),
                    b"not found",
                    uri="https://calendar.googleapis.com/",
                )

            return evenement

        return FauxRequeteEvenement(executer)

    def list(self, calendarId, **kwargs):
        def executer():
            evenements = list(self.agendas.get(calendarId, {}).values())
            return {"items": evenements}

        return FauxRequeteEvenement(executer)

    def patch(self, calendarId, eventId, body):
        def executer():
            self.nombre_patch += 1
            self.calendrier_modifie = calendarId
            self.corps_modification = body

            evenement = self.agendas[calendarId][eventId]
            evenement.update(body)

            return evenement

        return FauxRequeteEvenement(executer)


class FauxServiceDeplacement:
    def __init__(self, agendas):
        self.ressource_evenements = FauxEvenementsDeplacement(agendas)

    def events(self):
        return self.ressource_evenements


def creer_agenda_deplacement(evenement=None, calendrier="agenda_moussa"):
    agendas = {
        "agenda_aminata": {},
        "agenda_moussa": {},
        "agenda_khady": {},
    }

    if evenement is not None:
        agendas[calendrier][evenement["id"]] = evenement

    service = FauxServiceDeplacement(agendas)

    agenda = calendar.AgendaGoogle(
        service,
        {
            "aminata": "agenda_aminata",
            "moussa": "agenda_moussa",
            "khady": "agenda_khady",
        },
    )

    return agenda, service


def creer_evenement_test():
    return {
        "id": "evenement-test",
        "summary": "Visite appartement",
        "location": "Dakar",
        "description": "Visite avec le client",
        "start": {
            "dateTime": "2026-11-18T09:00:00+00:00",
            "timeZone": "Africa/Dakar",
        },
        "end": {
            "dateTime": "2026-11-18T09:45:00+00:00",
            "timeZone": "Africa/Dakar",
        },
    }


def test_deplacer_visite_avec_succes_exclut_evenement_actuel():
    evenement = creer_evenement_test()
    agenda, service = creer_agenda_deplacement(evenement)

    resultat = agenda.deplacer_visite(
        "evenement-test",
        "2026-11-18T09:15:00+00:00",
    )

    assert resultat == {"ok": True}
    assert service.ressource_evenements.nombre_patch == 1
    assert service.ressource_evenements.calendrier_modifie == "agenda_moussa"
    assert service.ressource_evenements.corps_modification["start"]["dateTime"] == (
        "2026-11-18T09:15:00+00:00"
    )
    assert service.ressource_evenements.corps_modification["end"]["dateTime"] == (
        "2026-11-18T10:00:00+00:00"
    )
    assert evenement["summary"] == "Visite appartement"
    assert evenement["location"] == "Dakar"


def test_deplacer_visite_refuse_un_creneau_occupe():
    evenement = creer_evenement_test()
    autre_evenement = {
        "id": "autre-evenement",
        "start": {"dateTime": "2026-11-18T10:00:00+00:00"},
        "end": {"dateTime": "2026-11-18T10:45:00+00:00"},
    }

    agenda, service = creer_agenda_deplacement(evenement)
    service.ressource_evenements.agendas["agenda_moussa"][
        "autre-evenement"
    ] = autre_evenement

    resultat = agenda.deplacer_visite(
        "evenement-test",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "CRENEAU_INDISPONIBLE"
    assert service.ressource_evenements.nombre_patch == 0


def test_deplacer_visite_refuse_un_evenement_introuvable():
    agenda, service = creer_agenda_deplacement()

    resultat = agenda.deplacer_visite(
        "evenement-inconnu",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
    assert service.ressource_evenements.nombre_patch == 0


def test_deplacer_visite_refuse_un_evenement_annule():
    evenement = creer_evenement_test()
    evenement["status"] = "cancelled"

    agenda, service = creer_agenda_deplacement(evenement)

    resultat = agenda.deplacer_visite(
        "evenement-test",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
    assert service.ressource_evenements.nombre_patch == 0


def test_deplacer_visite_refuse_une_date_invalide():
    evenement = creer_evenement_test()
    agenda, service = creer_agenda_deplacement(evenement)

    resultat = agenda.deplacer_visite(
        "evenement-test",
        "2026-11-18 10:00",
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"
    assert service.ressource_evenements.nombre_patch == 0


def test_deplacer_visite_retrouve_le_bon_agenda():
    evenement = creer_evenement_test()
    agenda, service = creer_agenda_deplacement(
        evenement,
        calendrier="agenda_khady",
    )

    resultat = agenda.deplacer_visite(
        "evenement-test",
        "2026-11-18T10:00:00+00:00",
    )

    assert resultat == {"ok": True}
    assert service.ressource_evenements.calendrier_modifie == "agenda_khady"

# tests de l'annulation de visite

class FauxEvenementsAnnulation:
    def __init__(self, agendas):
        self.agendas = agendas
        self.calendrier_supprime = None
        self.nombre_delete = 0

    def get(self, calendarId, eventId):
        def executer():
            evenement = self.agendas.get(calendarId, {}).get(eventId)

            if evenement is None:
                raise HttpError(
                    httplib2.Response({"status": "404", "reason": "Not Found"}),
                    b"not found",
                    uri="https://calendar.googleapis.com/",
                )

            return evenement

        return FauxRequeteEvenement(executer)

    def delete(self, calendarId, eventId):
        def executer():
            self.nombre_delete += 1
            self.calendrier_supprime = calendarId
            self.agendas[calendarId].pop(eventId)
            return {}

        return FauxRequeteEvenement(executer)


class FauxServiceAnnulation:
    def __init__(self, agendas):
        self.ressource_evenements = FauxEvenementsAnnulation(agendas)

    def events(self):
        return self.ressource_evenements


def creer_agenda_annulation(evenement=None, calendrier="agenda_moussa"):
    agendas = {
        "agenda_aminata": {},
        "agenda_moussa": {},
        "agenda_khady": {},
    }

    if evenement is not None:
        agendas[calendrier][evenement["id"]] = evenement

    service = FauxServiceAnnulation(agendas)

    agenda = calendar.AgendaGoogle(
        service,
        {
            "aminata": "agenda_aminata",
            "moussa": "agenda_moussa",
            "khady": "agenda_khady",
        },
    )

    return agenda, service


def test_annuler_visite_avec_succes():
    evenement = creer_evenement_test()
    agenda, service = creer_agenda_annulation(evenement)

    resultat = agenda.annuler_visite("evenement-test")

    assert resultat == {"ok": True}
    assert service.ressource_evenements.nombre_delete == 1
    assert service.ressource_evenements.calendrier_supprime == "agenda_moussa"
    assert "evenement-test" not in service.ressource_evenements.agendas["agenda_moussa"]


def test_annuler_visite_refuse_un_evenement_introuvable():
    agenda, service = creer_agenda_annulation()

    resultat = agenda.annuler_visite("evenement-inconnu")

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
    assert service.ressource_evenements.nombre_delete == 0


def test_annuler_visite_refuse_une_deuxieme_annulation():
    evenement = creer_evenement_test()
    evenement["status"] = "cancelled"

    agenda, service = creer_agenda_annulation(evenement)

    resultat = agenda.annuler_visite("evenement-test")

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
    assert service.ressource_evenements.nombre_delete == 0


def test_annuler_visite_retrouve_le_bon_agenda():
    evenement = creer_evenement_test()
    agenda, service = creer_agenda_annulation(
        evenement,
        calendrier="agenda_khady",
    )

    resultat = agenda.annuler_visite("evenement-test")

    assert resultat == {"ok": True}
    assert service.ressource_evenements.calendrier_supprime == "agenda_khady"

class FauxRequeteEtat:
    def __init__(self, calendrier_id, erreur=None):
        self.calendrier_id = calendrier_id
        self.erreur = erreur

    def execute(self):
        if self.erreur:
            raise self.erreur
        return {"items": []}


class FauxEvenementsEtat:
    def __init__(self, erreurs=None):
        self.erreurs = erreurs or {}
        self.appels = []

    def list(self, calendarId, maxResults):
        self.appels.append((calendarId, maxResults))
        return FauxRequeteEtat(
            calendarId,
            self.erreurs.get(calendarId),
        )


class FauxServiceEtat:
    def __init__(self, erreurs=None):
        self.evenements = FauxEvenementsEtat(erreurs)

    def events(self):
        return self.evenements


def creer_agenda_etat(erreurs=None):
    service = FauxServiceEtat(erreurs)
    agenda = calendar.AgendaGoogle(
        service,
        {
            "aminata": "agenda_aminata",
            "moussa": "agenda_moussa",
            "khady": "agenda_khady",
        },
    )
    return agenda, service


def test_verifier_etat_google_calendar():
    agenda, service = creer_agenda_etat()

    resultat = agenda.verifier_etat()

    assert resultat["ok"] is True
    assert isinstance(resultat["latence_ms"], int)
    assert resultat["latence_ms"] >= 0
    assert service.evenements.appels == [
        ("agenda_aminata", 1),
        ("agenda_moussa", 1),
        ("agenda_khady", 1),
    ]


def test_verifier_etat_refus_autorisation():
    erreur_http = HttpError(
        httplib2.Response({"status": "403"}),
        b"forbidden",
    )
    agenda, _ = creer_agenda_etat(
        {"agenda_aminata": erreur_http}
    )

    resultat = agenda.verifier_etat()

    assert resultat["ok"] is False
    assert resultat["code"] == "AUTORISATION"


def test_verifier_etat_calendrier_introuvable():
    erreur_http = HttpError(
        httplib2.Response({"status": "404"}),
        b"not found",
    )
    agenda, _ = creer_agenda_etat(
        {"agenda_moussa": erreur_http}
    )

    resultat = agenda.verifier_etat()

    assert resultat["ok"] is False
    assert resultat["code"] == "INTROUVABLE"
