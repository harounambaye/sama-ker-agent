"""Assemblage des quatre briques de l'agent et de leurs sondes d'état.

Tant que les PR de Fatou (serveur MCP) et de Papa (Google) ne sont pas fusionnées,
le catalogue est factice et Calendar/Gmail sont signalés « non branchés ».
"""

from __future__ import annotations

import time
from typing import Callable

import anthropic

from agent.config import Config
from contracts import erreur


def sonde_modele(cfg: Config, client: anthropic.Anthropic | None = None) -> Callable[[], dict]:
    """Clé acceptée et modèle configuré disponible, sans consommer de token."""
    client = client or anthropic.Anthropic(max_retries=1, timeout=8.0)

    def verifier_etat() -> dict:
        t0 = time.perf_counter()
        try:
            client.models.retrieve(cfg.model)
        except anthropic.AuthenticationError:
            return erreur("AUTORISATION", "Clé API refusée : vérifier ANTHROPIC_API_KEY dans .env.")
        except anthropic.PermissionDeniedError:
            return erreur("AUTORISATION", f"La clé n'a pas accès au modèle {cfg.model}.")
        except anthropic.NotFoundError:
            return erreur("ARGUMENT_INVALIDE", f"Modèle {cfg.model} introuvable : vérifier MODEL dans .env.")
        except anthropic.APIConnectionError:
            return erreur("INDISPONIBLE", "API du modèle injoignable (réseau).")
        except anthropic.APIStatusError as e:
            return erreur("INDISPONIBLE", f"API du modèle en erreur ({e.status_code}).")
        return {"ok": True, "latence_ms": round((time.perf_counter() - t0) * 1000)}

    return verifier_etat


def sonde_non_branchee(nom: str) -> Callable[[], dict]:
    def verifier_etat() -> dict:
        return {"ok": True, "latence_ms": 0, "mode": f"factice ({nom} pas encore branché)"}
    return verifier_etat


def sondes(cfg: Config, catalogue, agenda=None, messagerie=None) -> dict[str, Callable[[], dict]]:
    return {
        "modele": sonde_modele(cfg),
        "catalogue": catalogue.verifier_etat,
        "calendar": agenda.verifier_etat if agenda else sonde_non_branchee("Calendar"),
        "gmail": messagerie.verifier_etat if messagerie else sonde_non_branchee("Gmail"),
    }
