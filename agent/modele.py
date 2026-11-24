"""Appel « un coup » au modèle (sans boucle d'outils) : tri et rédaction du pipeline.

Sortie typée par `output_config.format` (json_schema) : le `tool_choice` forcé est
refusé (400) par les modèles récents, dont le modèle de secours. Si le modèle
principal est surchargé ou en panne, un second essai part sur MODEL_SECOURS.
Ne lève jamais : renvoie {"ok": True, ...} ou le format d'erreur commun.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic

from agent.config import Config
from agent.observabilite import instrumenter
from agent.traces import Trace
from contracts import erreur

_PANNE = (anthropic.InternalServerError, anthropic.APIConnectionError, anthropic.RateLimitError)


def client_par_defaut() -> anthropic.Anthropic:
    return instrumenter(anthropic.Anthropic(max_retries=2, timeout=60.0))


def appeler(
    client: anthropic.Anthropic,
    cfg: Config,
    trace: Trace,
    *,
    nom: str,
    systeme: str,
    contenu: str,
    schema: dict | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """{"ok", "texte" | "donnees", "tokens_entree", "tokens_sortie"} ou erreur."""
    output_config: dict[str, Any] = {"effort": cfg.effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    requete = dict(
        max_tokens=max_tokens or cfg.max_tokens_reponse,
        system=[{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": contenu}],
        output_config=output_config,
    )

    modeles = [cfg.model] + ([cfg.model_secours] if cfg.model_secours else [])
    for i, modele in enumerate(modeles):
        t0 = time.perf_counter()
        try:
            r = client.messages.create(model=modele, **requete)
            break
        except _PANNE as e:
            trace.evenement("erreur_modele", appel=nom, modele=modele, erreur=f"{type(e).__name__}: {e}")
            if i == len(modeles) - 1:
                return erreur("INDISPONIBLE", f"Modèle indisponible ({type(e).__name__}).")
        except anthropic.APIStatusError as e:  # 400, 401, 403, 404 : inutile de réessayer
            trace.evenement("erreur_modele", appel=nom, modele=modele, erreur=f"{type(e).__name__}: {e}")
            return erreur("INTERNE", f"Requête refusée par l'API du modèle ({e.status_code}).")

    u = r.usage
    tokens_entree = u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
    trace.evenement(
        "appel_modele", appel=nom, modele=r.model, stop_reason=r.stop_reason,
        tokens_entree=u.input_tokens, tokens_sortie=u.output_tokens,
        tokens_cache_lus=u.cache_read_input_tokens or 0,
        tokens_cache_ecrits=u.cache_creation_input_tokens or 0,
        duree_ms=round((time.perf_counter() - t0) * 1000),
    )
    compte = {"tokens_entree": tokens_entree, "tokens_sortie": u.output_tokens}
    if r.stop_reason == "refusal":
        return erreur("AUTORISATION", "Le modèle a refusé de traiter ce message.") | compte
    if r.stop_reason == "max_tokens":
        return erreur("INTERNE", "Réponse du modèle tronquée (max_tokens).") | compte

    texte = "\n".join(b.text for b in r.content if b.type == "text").strip()
    if schema is None:
        return {"ok": True, "texte": texte} | compte
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError:
        return erreur("INTERNE", "Sortie du modèle illisible (JSON attendu).") | compte
    if not isinstance(donnees, dict):
        return erreur("INTERNE", "Sortie du modèle inattendue (objet JSON attendu).") | compte
    return {"ok": True, "donnees": donnees} | compte
