"""Intégration Google Calendar."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from contracts import (
    Creneau,
    ResultatCreneaux,
    Conseiller,
    DUREE_VISITE_MIN,
    Erreur,
    FUSEAU,
    HEURE_FERMETURE,
    HEURE_OUVERTURE,
    JOURS_OUVRES,
    erreur,
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
