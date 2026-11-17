"""Mémoire des conversations : checkpointer SQLite de LangGraph.

Clé de conversation (thread_id) = identifiant du fil Gmail. Une conversation en
attente de validation survit à l'arrêt du processus ; quand le client répond
dans le même fil, l'agent retrouve tout le contexte.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def ouvrir_checkpointer(chemin: str | Path) -> SqliteSaver:
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(str(chemin), check_same_thread=False)
    return SqliteSaver(connexion)


def config_fil(fil_id: str, recursion_limit: int = 50) -> dict:
    return {"configurable": {"thread_id": fil_id}, "recursion_limit": recursion_limit}


def fils_connus(checkpointer: SqliteSaver) -> list[str]:
    """Identifiants des fils ayant au moins un état enregistré, sans doublon."""
    vus: dict[str, None] = {}
    for point in checkpointer.list(None):
        vus.setdefault(point.config["configurable"]["thread_id"], None)
    return list(vus)
