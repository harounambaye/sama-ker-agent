"""Intégration Google Calendar."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from contracts import (
    Confirmation,
    Creneau,
    ResultatCreneaux,
    ResultatVisite,
    Conseiller,
    DUREE_VISITE_MIN,
    Erreur,
    Etat,
    FUSEAU,
    HEURE_FERMETURE,
    HEURE_OUVERTURE,
    JOURS_OUVRES,
    erreur,
    id_evenement,
)
from integrations.google.auth import obtenir_identifiants


SCOPES_CALENDAR = [
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
]

PAS_CRENEAU_MIN = 15


def _charger_calendriers() -> dict[Conseiller, str] | Erreur:
    """Charge les identifiants des trois agendas depuis l'environnement."""
    calendriers: dict[Conseiller, str] = {}
    manquants: list[str] = []

    for conseiller in ("aminata", "moussa", "khady"):
        calendar_id = os.getenv(
            f"CALENDAR_ID_{conseiller.upper()}", ""
        ).strip()

        if not calendar_id:
            manquants.append(conseiller)
        else:
            calendriers[conseiller] = calendar_id

    if manquants:
        return erreur(
            "ARGUMENT_INVALIDE",
            f"Identifiants d'agendas manquants : {', '.join(manquants)}.",
        )

    return calendriers


def _parser_date(valeur: str) -> datetime | None:
    """Convertit une date ISO 8601 en date locale avec fuseau."""
    if not isinstance(valeur, str):
        return None

    try:
        date = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None

    if date.tzinfo is None or date.utcoffset() is None:
        return None

    return date.astimezone(ZoneInfo(FUSEAU))


class AgendaGoogle:
    """Client Google Calendar conforme au contrat Agenda."""

    def __init__(
        self,
        service: Any,
        calendriers: dict[Conseiller, str],
    ) -> None:
        self._service = service
        self._calendriers = calendriers

    @classmethod
    def connecter(cls) -> AgendaGoogle | Erreur:
        """Authentifie Google et initialise le service Calendar."""
        calendriers = _charger_calendriers()

        if isinstance(calendriers, dict) and calendriers.get("ok") is False:
            return calendriers

        identifiants = obtenir_identifiants(SCOPES_CALENDAR)

        if isinstance(identifiants, dict):
            return identifiants

        try:
            service = build(
                "calendar",
                "v3",
                credentials=identifiants,
                cache_discovery=False,
            )
        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Initialisation de Google Calendar impossible ({type(exc).__name__}).",
            )

        return cls(service, calendriers)

    def creer_visite(
        self,
        conseiller: Conseiller,
        debut: str,
        bien_id: str,
        adresse: str,
        client_nom: str,
        client_email: str,
        fil_id: str,
    ) -> ResultatVisite | Erreur:
        """Crée une visite après vérification de disponibilité."""
        if conseiller not in self._calendriers:
            return erreur(
                "ARGUMENT_INVALIDE",
                "Le conseiller demandé est inconnu.",
            )

        informations = (
            bien_id,
            adresse,
            client_nom,
            client_email,
            fil_id,
        )

        if not all(
            isinstance(valeur, str) and valeur.strip()
            for valeur in informations
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "Les informations du bien, du client et du fil sont obligatoires.",
            )

        debut_local = _parser_date(debut)

        if debut_local is None:
            return erreur(
                "ARGUMENT_INVALIDE",
                "La date de visite doit être au format ISO 8601 avec fuseau.",
            )

        if (
            debut_local.minute % PAS_CRENEAU_MIN != 0
            or debut_local.second != 0
            or debut_local.microsecond != 0
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "Le début de visite doit respecter un intervalle de 15 minutes.",
            )

        debut_iso = debut_local.isoformat()
        fin_local = debut_local + timedelta(minutes=DUREE_VISITE_MIN)
        evenement_id = id_evenement(fil_id, debut_iso)
        evenement_a_reactiver = None

        try:
            evenement = (
                self._service.events()
                .get(
                    calendarId=self._calendriers[conseiller],
                    eventId=evenement_id,
                )
                .execute()
            )

            if evenement:
                if evenement.get("status") == "cancelled":
                    evenement_a_reactiver = evenement
                else:
                    return {
                        "ok": True,
                        "evenement_id": evenement_id,
                        "deja_existante": True,
                    }

        except HttpError as exc:
            statut = getattr(exc.resp, "status", None)

            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Google a refusé l'accès à l'agenda.",
                )

            if statut != 404:
                return erreur(
                    "INDISPONIBLE",
                    f"Impossible de vérifier l'événement Google (HTTP {statut}).",
                )

        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Impossible de vérifier l'événement ({type(exc).__name__}).",
            )

        disponibilites = self.lister_creneaux_libres(
            conseiller,
            debut_iso,
            fin_local.isoformat(),
        )

        if not disponibilites.get("ok"):
            return disponibilites

        creneau_disponible = any(
            creneau["debut"] == debut_iso
            and creneau["conseiller"] == conseiller
            for creneau in disponibilites["creneaux"]
        )

        if not creneau_disponible:
            return erreur(
                "CRENEAU_INDISPONIBLE",
                "Ce créneau n'est plus disponible pour ce conseiller.",
            )

        evenement = {
            "id": evenement_id,
            "summary": f"Visite - {bien_id} - {client_nom}",
            "description": (
                f"Client : {client_nom}\n"
                f"Email : {client_email}\n"
                f"Bien : {bien_id}\n"
                f"Conseiller : {conseiller}\n"
                f"Fil Gmail : {fil_id}"
            ),
            "location": adresse,
            "start": {
                "dateTime": debut_iso,
                "timeZone": FUSEAU,
            },
            "end": {
                "dateTime": fin_local.isoformat(),
                "timeZone": FUSEAU,
            },
        }

        def reactiver_evenement(evenement_existant):
            corps = {
                **evenement_existant,
                **evenement,
                "status": "confirmed",
            }

            try:
                self._service.events().update(
                    calendarId=self._calendriers[conseiller],
                    eventId=evenement_id,
                    body=corps,
                ).execute()
            except HttpError as exc:
                statut = getattr(exc.resp, "status", None)

                if statut in (401, 403):
                    return erreur(
                        "AUTORISATION",
                        "Google a refus? la r?activation de la visite.",
                    )

                return erreur(
                    "INDISPONIBLE",
                    f"Impossible de r?activer la visite Google (HTTP {statut}).",
                )
            except Exception as exc:
                return erreur(
                    "INDISPONIBLE",
                    f"?chec de r?activation ({type(exc).__name__}).",
                )

            return None

        if evenement_a_reactiver is not None:
            resultat_erreur = reactiver_evenement(evenement_a_reactiver)

            if resultat_erreur is not None:
                return resultat_erreur

            return {
                "ok": True,
                "evenement_id": evenement_id,
                "deja_existante": False,
            }

        try:
            self._service.events().insert(
                calendarId=self._calendriers[conseiller],
                body=evenement,
            ).execute()

        except HttpError as exc:
            statut = getattr(exc.resp, "status", None)

            if statut == 409:
                try:
                    evenement_existant = (
                        self._service.events()
                        .get(
                            calendarId=self._calendriers[conseiller],
                            eventId=evenement_id,
                        )
                        .execute()
                    )
                except Exception:
                    return erreur(
                        "INDISPONIBLE",
                        "Le conflit Google est survenu, mais l'événement n'a pas pu être vérifié.",
                    )

                if evenement_existant:
                    if evenement_existant.get("status") == "cancelled":
                        resultat_erreur = reactiver_evenement(
                            evenement_existant
                        )

                        if resultat_erreur is not None:
                            return resultat_erreur

                        return {
                            "ok": True,
                            "evenement_id": evenement_id,
                            "deja_existante": False,
                        }

                    return {
                        "ok": True,
                        "evenement_id": evenement_id,
                        "deja_existante": True,
                    }

                return erreur(
                    "INDISPONIBLE",
                    "Google a signalé un conflit sans événement vérifiable.",
                )
            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Google a refusé la création de la visite.",
                )

            return erreur(
                "INDISPONIBLE",
                f"Impossible de créer la visite Google (HTTP {statut}).",
            )

        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Échec de création de la visite ({type(exc).__name__}).",
            )

        return {
            "ok": True,
            "evenement_id": evenement_id,
            "deja_existante": False,
        }
    def lister_creneaux_libres(
        self,
        conseiller: Conseiller | None,
        debut: str,
        fin: str,
    ) -> ResultatCreneaux | Erreur:
        """Retourne les visites de 45 minutes réellement disponibles."""
        debut_local = _parser_date(debut)
        fin_local = _parser_date(fin)

        if debut_local is None or fin_local is None:
            return erreur(
                "ARGUMENT_INVALIDE",
                "Les dates doivent être au format ISO 8601 avec fuseau horaire.",
            )

        if debut_local >= fin_local:
            return erreur(
                "ARGUMENT_INVALIDE",
                "La date de début doit précéder la date de fin.",
            )

        if conseiller is not None and conseiller not in self._calendriers:
            return erreur(
                "ARGUMENT_INVALIDE",
                "Le conseiller demandé est inconnu.",
            )

        conseillers = (
            [conseiller]
            if conseiller is not None
            else list(self._calendriers)
        )

        if not conseillers:
            return erreur(
                "INDISPONIBLE",
                "Aucun agenda Google n'est configuré.",
            )

        calendriers_ids = {
            self._calendriers[nom]: nom for nom in conseillers
        }

        corps = {
            "timeMin": debut_local.isoformat(),
            "timeMax": fin_local.isoformat(),
            "timeZone": FUSEAU,
            "items": [{"id": calendar_id} for calendar_id in calendriers_ids],
        }

        try:
            reponse = (
                self._service.freebusy()
                .query(body=corps)
                .execute(num_retries=2)
            )
        except HttpError as exc:
            statut = getattr(exc.resp, "status", None)

            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Google a refusé l'accès aux agendas.",
                )

            if statut == 404:
                return erreur(
                    "INTROUVABLE",
                    "Un agenda Google demandé est introuvable.",
                )

            return erreur(
                "INDISPONIBLE",
                f"Erreur Google Calendar (HTTP {statut}).",
            )
        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Impossible de consulter Google Calendar ({type(exc).__name__}).",
            )

        calendriers_reponse = reponse.get("calendars", {})

        if not isinstance(calendriers_reponse, dict):
            return erreur(
                "INTERNE",
                "La réponse de Google Calendar est invalide.",
            )

        occupations: dict[Conseiller, list[tuple[datetime, datetime]]] = {}

        for calendar_id, nom in calendriers_ids.items():
            details = calendriers_reponse.get(calendar_id)

            if not isinstance(details, dict):
                return erreur(
                    "INTROUVABLE",
                    f"Impossible de récupérer l'agenda de {nom}.",
                )

            erreurs_google = details.get("errors", [])

            if erreurs_google:
                raison = erreurs_google[0].get("reason", "")

                if raison == "forbidden":
                    return erreur(
                        "AUTORISATION",
                        f"Accès refusé à l'agenda de {nom}.",
                    )

                if raison == "notFound":
                    return erreur(
                        "INTROUVABLE",
                        f"L'agenda de {nom} est introuvable.",
                    )

                return erreur(
                    "INDISPONIBLE",
                    f"Google ne peut pas consulter l'agenda de {nom}.",
                )

            periodes: list[tuple[datetime, datetime]] = []

            for occupation in details.get("busy", []):
                debut_occupation = _parser_date(occupation.get("start", ""))
                fin_occupation = _parser_date(occupation.get("end", ""))

                if (
                    debut_occupation is None
                    or fin_occupation is None
                    or debut_occupation >= fin_occupation
                ):
                    return erreur(
                        "INTERNE",
                        f"Une période occupée de l'agenda {nom} est invalide.",
                    )

                periodes.append((debut_occupation, fin_occupation))

            occupations[nom] = periodes

        fuseau = ZoneInfo(FUSEAU)
        duree = timedelta(minutes=DUREE_VISITE_MIN)
        pas = timedelta(minutes=PAS_CRENEAU_MIN)
        creneaux: list[Creneau] = []

        jour = debut_local.date()

        while jour <= fin_local.date():
            if jour.weekday() in JOURS_OUVRES:
                candidat = datetime.combine(
                    jour,
                    time(HEURE_OUVERTURE),
                    tzinfo=fuseau,
                )
                fermeture = datetime.combine(
                    jour,
                    time(HEURE_FERMETURE),
                    tzinfo=fuseau,
                )

                while candidat + duree <= fermeture:
                    fin_candidat = candidat + duree

                    if (
                        candidat >= debut_local
                        and fin_candidat <= fin_local
                    ):
                        for nom in conseillers:
                            est_libre = all(
                                candidat >= fin_occupation
                                or fin_candidat <= debut_occupation
                                for debut_occupation, fin_occupation
                                in occupations[nom]
                            )

                            if est_libre:
                                creneaux.append(
                                    {
                                        "conseiller": nom,
                                        "debut": candidat.isoformat(),
                                        "fin": fin_candidat.isoformat(),
                                    }
                                )

                    candidat += pas

            jour += timedelta(days=1)

        return {"ok": True, "creneaux": creneaux}



    def deplacer_visite(
        self,
        evenement_id: str,
        nouveau_debut: str,
    ) -> Confirmation | Erreur:
        """Déplace une visite après vérification du nouveau créneau."""
        if (
            not isinstance(evenement_id, str)
            or not evenement_id.strip()
            or not isinstance(nouveau_debut, str)
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "L'identifiant ou la nouvelle date est invalide.",
            )

        debut = _parser_date(nouveau_debut)

        if debut is None:
            return erreur(
                "ARGUMENT_INVALIDE",
                "La nouvelle date doit être au format ISO 8601 avec fuseau.",
            )

        duree = timedelta(minutes=DUREE_VISITE_MIN)
        fin = debut + duree

        if (
            debut.minute % PAS_CRENEAU_MIN != 0
            or debut.second != 0
            or debut.microsecond != 0
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "Le début doit respecter un intervalle de 15 minutes.",
            )

        if (
            debut.weekday() not in JOURS_OUVRES
            or debut.time() < time(HEURE_OUVERTURE)
            or fin.time() > time(HEURE_FERMETURE)
            or fin.date() != debut.date()
        ):
            return erreur(
                "CRENEAU_INDISPONIBLE",
                "La visite doit respecter les jours et horaires d'ouverture.",
            )

        try:
            evenements = self._service.events()
            evenement_id = evenement_id.strip()
        except Exception:
            return erreur(
                "INDISPONIBLE",
                "Impossible de consulter Google Calendar.",
            )
        evenement = None
        calendrier_trouve = None

        for calendrier_id in self._calendriers.values():
            try:
                evenement = evenements.get(
                    calendarId=calendrier_id,
                    eventId=evenement_id,
                ).execute()
                calendrier_trouve = calendrier_id
                break

            except HttpError as exc:
                statut = exc.resp.status

                if statut == 404:
                    continue

                if statut in (401, 403):
                    return erreur(
                        "AUTORISATION",
                        "Accès refusé à Google Calendar.",
                    )

                return erreur(
                    "INDISPONIBLE",
                    "Impossible de retrouver la visite dans Google Calendar.",
                )

            except Exception:
                return erreur(
                    "INDISPONIBLE",
                    "Impossible de consulter Google Calendar.",
                )

        if evenement is None or calendrier_trouve is None:
            return erreur(
                "INTROUVABLE",
                "La visite demandée est introuvable.",
            )

        if evenement.get("status") == "cancelled":
            return erreur(
                "INTROUVABLE",
                "La visite demand?e est introuvable.",
            )

        def parser_horaire(valeur: dict) -> datetime | None:
            """Convertit un horaire Google en date locale."""
            date_heure = valeur.get("dateTime")

            if date_heure:
                return _parser_date(date_heure)

            date_jour = valeur.get("date")

            if date_jour:
                try:
                    jour = datetime.fromisoformat(date_jour).date()
                    return datetime.combine(
                        jour,
                        time.min,
                        tzinfo=ZoneInfo(FUSEAU),
                    )
                except (TypeError, ValueError):
                    return None

            return None

        try:
            page_token = None

            while True:
                parametres = {
                    "calendarId": calendrier_trouve,
                    "timeMin": debut.isoformat(),
                    "timeMax": fin.isoformat(),
                    "singleEvents": True,
                    "orderBy": "startTime",
                    "maxResults": 2500,
                }

                if page_token:
                    parametres["pageToken"] = page_token

                reponse = evenements.list(**parametres).execute()

                if not isinstance(reponse, dict):
                    return erreur(
                        "INTERNE",
                        "La réponse de Google Calendar est invalide.",
                    )

                liste_evenements = reponse.get("items", [])

                if not isinstance(liste_evenements, list):
                    return erreur(
                        "INTERNE",
                        "La liste des événements Google est invalide.",
                    )

                for autre in liste_evenements:
                    if (
                        autre.get("id") == evenement_id
                        or autre.get("status") == "cancelled"
                    ):
                        continue

                    debut_autre = parser_horaire(autre.get("start", {}))
                    fin_autre = parser_horaire(autre.get("end", {}))

                    if (
                        debut_autre is None
                        or fin_autre is None
                        or debut_autre >= fin_autre
                    ):
                        return erreur(
                            "INTERNE",
                            "Un événement de l'agenda possède des horaires invalides.",
                        )

                    if debut < fin_autre and fin > debut_autre:
                        return erreur(
                            "CRENEAU_INDISPONIBLE",
                            "Le nouveau créneau est déjà occupé.",
                        )

                page_token = reponse.get("nextPageToken")

                if not page_token:
                    break

            evenements.patch(
                calendarId=calendrier_trouve,
                eventId=evenement_id,
                body={
                    "start": {
                        "dateTime": debut.isoformat(),
                        "timeZone": FUSEAU,
                    },
                    "end": {
                        "dateTime": fin.isoformat(),
                        "timeZone": FUSEAU,
                    },
                },
            ).execute()

            return {"ok": True}

        except HttpError as exc:
            statut = exc.resp.status

            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Accès refusé lors du déplacement de la visite.",
                )

            if statut == 404:
                return erreur(
                    "INTROUVABLE",
                    "La visite ou l'agenda n'existe plus.",
                )

            if statut == 409:
                return erreur(
                    "CRENEAU_INDISPONIBLE",
                    "Le créneau vient d'être réservé.",
                )

            return erreur(
                "INDISPONIBLE",
                "Google Calendar n'a pas pu déplacer la visite.",
            )

        except Exception:
            return erreur(
                "INDISPONIBLE",
                "Une erreur empêche le déplacement de la visite.",
            )

    def annuler_visite(
        self,
        evenement_id: str,
    ) -> Confirmation | Erreur:
        """Annule une visite dans son agenda Google."""
        if not isinstance(evenement_id, str) or not evenement_id.strip():
            return erreur(
                "ARGUMENT_INVALIDE",
                "L'identifiant de la visite est invalide.",
            )

        evenement_id = evenement_id.strip()

        try:
            evenements = self._service.events()
        except Exception:
            return erreur(
                "INDISPONIBLE",
                "Impossible de consulter Google Calendar.",
            )

        calendrier_trouve = None
        evenement_trouve = None

        for calendrier_id in self._calendriers.values():
            try:
                evenement_trouve = evenements.get(
                    calendarId=calendrier_id,
                    eventId=evenement_id,
                ).execute()

                calendrier_trouve = calendrier_id
                break

            except HttpError as exc:
                statut = exc.resp.status

                if statut == 404:
                    continue

                if statut in (401, 403):
                    return erreur(
                        "AUTORISATION",
                        "Accès refusé à Google Calendar.",
                    )

                return erreur(
                    "INDISPONIBLE",
                    "Impossible de retrouver la visite dans Google Calendar.",
                )

            except Exception:
                return erreur(
                    "INDISPONIBLE",
                    "Impossible de consulter Google Calendar.",
                )

        if calendrier_trouve is None:
            return erreur(
                "INTROUVABLE",
                "La visite demandée est introuvable.",
            )

        if evenement_trouve.get("status") == "cancelled":
            return erreur(
                "INTROUVABLE",
                "La visite demand?e est introuvable.",
            )

        try:
            evenements.delete(
                calendarId=calendrier_trouve,
                eventId=evenement_id,
            ).execute()

            return {"ok": True}

        except HttpError as exc:
            statut = exc.resp.status

            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Accès refusé lors de l'annulation de la visite.",
                )

            if statut == 404:
                return erreur(
                    "INTROUVABLE",
                    "La visite ou l'agenda n'existe plus.",
                )

            return erreur(
                "INDISPONIBLE",
                "Google Calendar n'a pas pu annuler la visite.",
            )

        except Exception:
            return erreur(
                "INDISPONIBLE",
                "Une erreur empêche l'annulation de la visite.",
            )

    def verifier_etat(self) -> Etat | Erreur:
        """Verifie l'acces en lecture aux trois agendas Google."""
        debut = perf_counter()

        try:
            evenements = self._service.events()

            for calendrier_id in self._calendriers.values():
                resultat = evenements.list(
                    calendarId=calendrier_id,
                    maxResults=1,
                ).execute()

                if not isinstance(resultat, dict):
                    return erreur(
                        "INTERNE",
                        "La reponse de Google Calendar est invalide.",
                    )

            latence_ms = int((perf_counter() - debut) * 1000)

            return {
                "ok": True,
                "latence_ms": latence_ms,
            }

        except HttpError as exc:
            statut = exc.resp.status

            if statut in (401, 403):
                return erreur(
                    "AUTORISATION",
                    "Acces refuse a Google Calendar.",
                )

            if statut == 404:
                return erreur(
                    "INTROUVABLE",
                    "Un agenda Google Calendar est introuvable.",
                )

            return erreur(
                "INDISPONIBLE",
                "Google Calendar ne repond pas correctement.",
            )

        except Exception:
            return erreur(
                "INDISPONIBLE",
                "Impossible de verifier la connexion a Google Calendar.",
            )
