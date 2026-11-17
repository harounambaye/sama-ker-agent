"""Authentification OAuth partagée par les intégrations Google."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from contracts import Erreur, erreur

load_dotenv()


def _sauvegarder_identifiants(
    identifiants: Credentials,
    chemin: Path,
) -> Erreur | None:
    """Enregistre le jeton OAuth localement."""
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(identifiants.to_json(), encoding="utf-8")
    except OSError:
        return erreur("INTERNE", "Impossible d'enregistrer le jeton Google.")
    return None


def obtenir_identifiants(scopes: Sequence[str]) -> Credentials | Erreur:
    """Charge, renouvelle ou demande les autorisations Google nécessaires."""
    scopes_demandes = list(dict.fromkeys(scopes))

    if not scopes_demandes or not all(scopes_demandes):
        return erreur("ARGUMENT_INVALIDE", "Les permissions Google sont invalides.")

    chemin_credentials = Path(
        os.getenv("GOOGLE_CREDENTIALS", "secrets/credentials.json")
    )
    chemin_token = Path(
        os.getenv("GOOGLE_TOKEN", "secrets/token.json")
    )

    if not chemin_credentials.is_file():
        return erreur(
            "ARGUMENT_INVALIDE",
            "Fichier OAuth Google absent : vérifiez GOOGLE_CREDENTIALS.",
        )

    identifiants = None

    if chemin_token.is_file():
        try:
            identifiants = Credentials.from_authorized_user_file(
                str(chemin_token)
            )
        except (OSError, ValueError):
            identifiants = None

    scopes_existants = list(identifiants.scopes or []) if identifiants else []
    scopes_complets = list(dict.fromkeys(scopes_existants + scopes_demandes))

    if (
        identifiants
        and identifiants.valid
        and identifiants.has_scopes(scopes_demandes)
    ):
        return identifiants

    if (
        identifiants
        and identifiants.expired
        and identifiants.refresh_token
        and identifiants.has_scopes(scopes_demandes)
    ):
        try:
            identifiants.refresh(Request())
        except RefreshError:
            identifiants = None
        except TransportError:
            return erreur("INDISPONIBLE", "Impossible de joindre Google pour renouveler le jeton.")

        if identifiants and identifiants.valid:
            sauvegarde = _sauvegarder_identifiants(
                identifiants, chemin_token
            )
            return sauvegarde or identifiants

    try:
        flux = InstalledAppFlow.from_client_secrets_file(
            str(chemin_credentials),
            scopes=scopes_complets,
        )
        identifiants = flux.run_local_server(port=0, open_browser=True)
    except Exception as exc:
        return erreur(
            "AUTORISATION",
            f"Authentification Google impossible ({type(exc).__name__}).",
        )

    if not identifiants.has_scopes(scopes_complets):
        return erreur(
            "AUTORISATION",
            "Les permissions Google demandées n'ont pas été accordées.",
        )

    sauvegarde = _sauvegarder_identifiants(identifiants, chemin_token)
    return sauvegarde or identifiants
