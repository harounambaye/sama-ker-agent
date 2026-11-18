"""Boîte à outils branchée sur le serveur MCP du catalogue (exercice 2).

Le graphe est synchrone et exécute les outils dans des threads ; le client MCP est
asynchrone. La session MCP vit donc dans sa propre boucle asyncio, sur un thread
dédié, ouverte une fois au démarrage et gardée pour tous les appels :
`appeler()` y soumet chaque requête et attend la réponse avec un délai.

Cibles possibles :
    StdioServerParameters(...)   l'agent lance le serveur (MCP_TRANSPORT=stdio)
    "http://127.0.0.1:8000/mcp"  serveur déjà lancé (MCP_TRANSPORT=http)
    l'objet MCPServer lui-même   en mémoire, pour les tests

Aucune exception ne remonte vers la boucle : tout est rendu au format commun
{"ok": false, "code", "message"}.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import TimeoutError as DelaiDepasse
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment

from contracts import erreur

# Appelé par le code du graphe (sondes d'état), jamais proposé au modèle.
OUTILS_INTERNES = {"verifier_etat"}


def cible_depuis_env() -> StdioServerParameters | str:
    if os.getenv("MCP_TRANSPORT", "stdio").lower() == "http":
        return os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
    # Environnement minimal + CATALOGUE_DB : le serveur ne reçoit jamais la clé API.
    env = get_default_environment()
    if os.getenv("CATALOGUE_DB"):
        env["CATALOGUE_DB"] = os.environ["CATALOGUE_DB"]
    return StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.serveur"], env=env)


def _cause(e: BaseException) -> str:
    """Première cause réelle, sous les ExceptionGroup d'anyio."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__}: {e}"


def _nettoyer_schema(schema: dict) -> dict:
    """Schéma pydantic -> schéma lisible : « X ou null » devient « X » (argument facultatif),
    les titres générés sont retirés. Le serveur reste juge de la validation."""
    if not isinstance(schema, dict):
        return schema
    propre = {k: _nettoyer_schema(v) if isinstance(v, dict) else v
              for k, v in schema.items() if k != "title"}
    if "properties" in propre:
        propre["properties"] = {n: _nettoyer_schema(p) for n, p in propre["properties"].items()}
    variantes = propre.get("anyOf")
    if isinstance(variantes, list):
        utiles = [v for v in variantes if v.get("type") != "null"]
        if len(utiles) == 1:
            del propre["anyOf"]
            propre.update(utiles[0])
            if propre.get("default") is None:
                propre.pop("default", None)
    return propre


class OutilsMCP:
    """contracts.Catalogue côté agent, à travers une session MCP persistante."""

    def __init__(self, cible: Any = None, delai_s: float = 15.0):
        self._cible = cible if cible is not None else cible_depuis_env()
        self._delai_s = delai_s
        self._boucle = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._boucle.run_forever, daemon=True,
                                        name="session-mcp")
        self._client: Client | None = None
        self._arret: asyncio.Event | None = None
        self._definitions: list[dict] | None = None
        self._echec_connexion: str | None = None
        self._thread.start()
        self._connecter()

    # ------------------------------------------------------------ session --- #

    def _connecter(self) -> None:
        pret = threading.Event()

        async def session() -> None:
            self._arret = asyncio.Event()
            try:
                # mode="legacy" : poignée de main initialize classique. En mcp 2.3, la sonde
                # server/discover du mode "auto" coupe la connexion HTTP au lieu de se replier.
                async with Client(self._cible, mode="legacy") as client:
                    self._client = client
                    pret.set()
                    await self._arret.wait()
            except Exception as e:  # serveur introuvable, base absente, port fermé...
                self._echec_connexion = _cause(e)
            finally:
                self._client = None
                pret.set()

        asyncio.run_coroutine_threadsafe(session(), self._boucle)
        if not pret.wait(self._delai_s):
            self._echec_connexion = f"pas de réponse du serveur MCP en {self._delai_s:.0f} s"

    def _executer(self, coro_fn) -> Any:
        if self._client is None:
            raise ConnectionError(self._echec_connexion or "session MCP fermée")
        futur = asyncio.run_coroutine_threadsafe(coro_fn(self._client), self._boucle)
        try:
            return futur.result(self._delai_s)
        except DelaiDepasse:
            futur.cancel()
            raise

    def fermer(self) -> None:
        if self._arret is not None:
            self._boucle.call_soon_threadsafe(self._arret.set)
        self._boucle.call_soon_threadsafe(self._boucle.stop)
        self._thread.join(timeout=5)

    def __enter__(self) -> "OutilsMCP":
        return self

    def __exit__(self, *_) -> None:
        self.fermer()

    # ------------------------------------------------------- BoiteAOutils --- #

    def definitions(self) -> list[dict]:
        """Outils exposés par le serveur, au format de l'API Claude. Liste vide si le
        serveur est injoignable : la sonde d'état bloque alors le lancement."""
        if self._definitions is None:
            try:
                outils = self._executer(lambda c: c.list_tools()).tools
            except Exception:
                return []
            self._definitions = [
                {"name": o.name, "description": o.description or "",
                 "input_schema": _nettoyer_schema(o.input_schema)}
                for o in outils if o.name not in OUTILS_INTERNES
            ]
        return self._definitions

    def appeler(self, nom: str, arguments: dict[str, Any]) -> dict:
        try:
            r = self._executer(lambda c: c.call_tool(nom, arguments))
        except DelaiDepasse:
            return erreur("DELAI_DEPASSE", f"Le catalogue n'a pas répondu en {self._delai_s:.0f} s.")
        except Exception as e:
            return erreur("INDISPONIBLE", f"Serveur MCP du catalogue injoignable ({_cause(e)}). "
                                          "Ne propose aucun bien de mémoire.")
        texte = "".join(getattr(b, "text", "") for b in r.content)
        if r.is_error:
            # Validation des arguments ou outil inconnu : le modèle peut se corriger.
            return erreur("ARGUMENT_INVALIDE", texte or f"{nom} a refusé ses arguments.")
        if isinstance(r.structured_content, dict) and "ok" in r.structured_content:
            return r.structured_content
        try:
            resultat = json.loads(texte)
        except json.JSONDecodeError:
            return erreur("INTERNE", f"Réponse illisible du serveur pour {nom} : {texte[:200]}")
        return resultat if isinstance(resultat, dict) else erreur(
            "INTERNE", f"Réponse inattendue du serveur pour {nom}.")

    def verifier_etat(self) -> dict:
        """Sonde de la brique catalogue : la session répond ET la base est saine."""
        if self._client is None:
            return erreur("INDISPONIBLE", f"Serveur MCP injoignable ({self._echec_connexion}). "
                                          "Vérifier MCP_TRANSPORT / MCP_URL, ou que le serveur "
                                          "démarre : python -m mcp_server.serveur")
        return self.appeler("verifier_etat", {})
