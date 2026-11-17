"""Initialisation de l'intégration Google Calendar."""

from __future__ import annotations

import os
from typing import Any

from googleapiclient.discovery import build

from contracts import Conseiller, Erreur, erreur
from integrations.google.auth import obtenir_identifiants


SCOPES_CALENDAR = [
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
]


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
