"""Integration Google Gmail."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build

from contracts import Erreur, erreur
from integrations.google.auth import obtenir_identifiants


SCOPES_GMAIL = [
    "https://www.googleapis.com/auth/gmail.modify",
]


class MessagerieGoogle:
    """Client Google Gmail conforme au contrat Messagerie."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def connecter(cls) -> MessagerieGoogle | Erreur:
        """Authentifie Google et initialise le service Gmail."""
        identifiants = obtenir_identifiants(SCOPES_GMAIL)

        if isinstance(identifiants, dict):
            return identifiants

        try:
            service = build(
                "gmail",
                "v1",
                credentials=identifiants,
                cache_discovery=False,
            )
        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Initialisation de Google Gmail impossible ({type(exc).__name__}).",
            )

        return cls(service)
