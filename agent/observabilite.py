"""LangSmith, en option : traces des exécutions du graphe et des appels au modèle.

Activé seulement si LANGSMITH_TRACING=true et LANGSMITH_API_KEY sont dans .env :
- LangGraph envoie alors chaque exécution (nœuds, état en entrée et en sortie) ;
- le client Anthropic est instrumenté (wrap_anthropic) : chaque appel au modèle
  apparaît avec ses messages, sa réponse, ses tokens et sa durée.
Sans ces variables, rien ne quitte la machine : seules les traces JSONL locales existent.
"""

from __future__ import annotations

import os

import anthropic


def langsmith_actif() -> bool:
    return (os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"
            and bool(os.getenv("LANGSMITH_API_KEY", "").strip()))


def instrumenter(client: anthropic.Anthropic) -> anthropic.Anthropic:
    """Le même client, tracé dans LangSmith si celui-ci est actif."""
    if not langsmith_actif():
        return client
    from langsmith.wrappers import wrap_anthropic
    return wrap_anthropic(client)
