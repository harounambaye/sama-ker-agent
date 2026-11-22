"""Assemblage des quatre briques de l'agent et de leurs sondes d'état.

Catalogue : serveur MCP de Fatou par défaut (CATALOGUE=mcp), ou catalogue factice
en mémoire (CATALOGUE=factice) pour travailler sans serveur. Calendar et Gmail :
factices (BRIQUES=factice) ou intégrations Google de Papa (BRIQUES=google).
"""

from __future__ import annotations

import os
import time
from typing import Callable

import anthropic

from agent.config import Config
from agent.outils import BoiteAOutils
from contracts import erreur


def catalogue() -> tuple[BoiteAOutils, object]:
    """(outils proposés au modèle, brique exposant verifier_etat) selon CATALOGUE."""
    mode = os.getenv("CATALOGUE", "mcp").lower()
    if mode == "factice":
        from agent.catalogue_factice import CatalogueFactice
        from agent.outils import OutilsCatalogueLocal
        brique = CatalogueFactice()
        return OutilsCatalogueLocal(brique), brique
    if mode != "mcp":
        raise SystemExit(f"CATALOGUE={mode!r} inconnu : mcp ou factice.")
    from agent.outils_mcp import OutilsMCP
    outils = OutilsMCP()
    return outils, outils


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


def agenda_et_messagerie() -> tuple[object, object]:
    """Calendar et Gmail selon BRIQUES : « factice » (défaut, enregistrés dans FACTICES_DIR)
    ou « google » (intégrations de Papa, compte de test et OAuth)."""
    mode = os.getenv("BRIQUES", "factice").lower()
    if mode == "factice":
        from pathlib import Path

        from agent.factices import AgendaFactice, MessagerieFactice
        dossier = Path(os.getenv("FACTICES_DIR", "data/factices"))
        return AgendaFactice(dossier / "agenda.json"), MessagerieFactice(dossier / "messagerie.json")
    if mode != "google":
        raise SystemExit(f"BRIQUES={mode!r} inconnu : factice ou google.")
    from integrations.google.calendar import AgendaGoogle
    from integrations.google.gmail import MessagerieGoogle
    agenda, messagerie = AgendaGoogle.connecter(), MessagerieGoogle.connecter()
    for nom, brique in (("Google Calendar", agenda), ("Gmail", messagerie)):
        if isinstance(brique, dict):  # erreur au format commun
            raise SystemExit(f"{nom} : [{brique['code']}] {brique['message']}")
    return agenda, messagerie
