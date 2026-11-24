"""Boucle de l'agent (exercice 1) sous forme de graphe LangGraph.

    START -> modele
    modele -- tool_use ----------------> outils -> modele
    modele -- fin, refus, erreur ------> END
    modele -- étapes/tokens épuisés ---> limite -> END

Le modèle est appelé avec le SDK officiel `anthropic` ; LangGraph porte l'état,
les bornes de la boucle et, plus tard, les pauses de validation humaine.
"""

from __future__ import annotations

import json
import operator
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from agent.config import Config
from agent.observabilite import instrumenter
from agent.outils import BoiteAOutils
from agent.prompts import SYSTEME
from agent.traces import Trace

Statut = Literal["en_cours", "termine", "limite", "refus", "erreur_modele"]


class EtatAgent(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]   # historique au format Messages API
    etapes: int                                     # nombre d'appels au modèle
    tokens_entree: int
    tokens_sortie: int
    appels_outils: int
    statut: Statut
    reponse: str


MESSAGE_LIMITE = (
    "Je n'ai pas pu finaliser cette recherche automatiquement. "
    "Un conseiller de l'agence va reprendre votre demande."
)
MESSAGE_ERREUR_MODELE = (
    "Le service est momentanément indisponible. "
    "Un conseiller de l'agence va reprendre votre demande."
)


def construire_graphe(
    cfg: Config,
    outils: BoiteAOutils,
    trace: Trace,
    client: anthropic.Anthropic | None = None,
):
    """Graphe de l'exercice 1 : la boucle seule, de START à END."""
    g = StateGraph(EtatAgent)
    g.add_edge(START, "modele")
    ajouter_boucle(g, cfg, outils, trace, client)
    return g.compile()


def ajouter_boucle(
    g: StateGraph,
    cfg: Config,
    outils: BoiteAOutils,
    trace: Trace,
    client: anthropic.Anthropic | None = None,
    suite: str = END,
) -> None:
    """Ajoute à `g` les nœuds modele, outils et limite.

    Le graphe appelant relie son entrée à "modele" ; quand la boucle s'arrête
    (réponse, limite, refus ou erreur), elle passe au nœud `suite`, qui lit
    `statut` et `reponse` dans l'état.
    """
    client = client or instrumenter(anthropic.Anthropic(max_retries=2, timeout=60.0))
    definitions = outils.definitions()
    systeme = [{"type": "text", "text": SYSTEME}]

    # ------------------------------------------------------------------ #
    def appeler_modele(etat: EtatAgent) -> dict:
        etape = etat.get("etapes", 0) + 1
        t0 = time.perf_counter()
        try:
            r = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens_reponse,
                system=systeme,
                tools=definitions,
                messages=etat["messages"],
                output_config={"effort": cfg.effort},
                cache_control={"type": "ephemeral"},  # outils + système + historique
            )
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            trace.evenement("erreur_modele", etape=etape, erreur=f"{type(e).__name__}: {e}")
            return {"etapes": etape, "statut": "erreur_modele", "reponse": MESSAGE_ERREUR_MODELE}

        u = r.usage
        trace.evenement(
            "appel_modele", etape=etape, modele=r.model, stop_reason=r.stop_reason,
            tokens_entree=u.input_tokens, tokens_sortie=u.output_tokens,
            tokens_cache_lus=u.cache_read_input_tokens or 0,
            tokens_cache_ecrits=u.cache_creation_input_tokens or 0,
            duree_ms=round((time.perf_counter() - t0) * 1000),
        )
        contenu = [b.model_dump(mode="json", exclude_none=True) for b in r.content]
        texte = "\n".join(b.text for b in r.content if b.type == "text").strip()
        maj: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": contenu}],
            "etapes": etape,
            "tokens_entree": etat.get("tokens_entree", 0) + u.input_tokens
            + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
            "tokens_sortie": etat.get("tokens_sortie", 0) + u.output_tokens,
        }
        if r.stop_reason == "tool_use":
            maj["statut"] = "en_cours"
        elif r.stop_reason == "refusal":
            maj |= {"statut": "refus", "reponse": MESSAGE_LIMITE}
        elif r.stop_reason == "max_tokens":
            maj |= {"statut": "limite", "reponse": texte or MESSAGE_LIMITE}
        else:  # end_turn, stop_sequence
            maj |= {"statut": "termine", "reponse": texte}
        return maj

    # ------------------------------------------------------------------ #
    def executer_un(bloc: dict) -> dict:
        t0 = time.perf_counter()
        resultat = outils.appeler(bloc["name"], bloc.get("input") or {})
        trace.evenement(
            "appel_outil", outil=bloc["name"], arguments=bloc.get("input") or {},
            resultat=resultat, duree_ms=round((time.perf_counter() - t0) * 1000),
        )
        return {
            "type": "tool_result",
            "tool_use_id": bloc["id"],
            "content": json.dumps(resultat, ensure_ascii=False),
            "is_error": not resultat.get("ok", False),
        }

    def executer_outils(etat: EtatAgent) -> dict:
        appels = [b for b in etat["messages"][-1]["content"] if b.get("type") == "tool_use"]
        # Appels parallèles ; tous les résultats repartent dans UN seul message.
        with ThreadPoolExecutor(max_workers=4) as pool:
            resultats = list(pool.map(executer_un, appels))
        return {
            "messages": [{"role": "user", "content": resultats}],
            "appels_outils": etat.get("appels_outils", 0) + len(appels),
        }

    # ------------------------------------------------------------------ #
    def limite(etat: EtatAgent) -> dict:
        trace.evenement("limite_atteinte", etapes=etat.get("etapes"),
                        tokens=etat.get("tokens_entree", 0) + etat.get("tokens_sortie", 0))
        return {"statut": "limite", "reponse": MESSAGE_LIMITE}

    def apres_modele(etat: EtatAgent) -> str:
        if etat["statut"] != "en_cours":
            return suite
        tokens = etat.get("tokens_entree", 0) + etat.get("tokens_sortie", 0)
        if etat["etapes"] >= cfg.max_etapes or tokens >= cfg.max_tokens_email:
            return "limite"
        return "outils"

    g.add_node("modele", appeler_modele)
    g.add_node("outils", executer_outils)
    g.add_node("limite", limite)
    g.add_conditional_edges("modele", apres_modele, ["outils", "limite", suite])
    g.add_edge("outils", "modele")
    g.add_edge("limite", suite)


def executer(graphe, cfg: Config, demande: str, trace: Trace) -> EtatAgent:
    """Traite une demande de bout en bout et renvoie l'état final."""
    trace.evenement("debut", demande=demande, modele=cfg.model)
    t0 = time.perf_counter()
    etat = graphe.invoke(
        {"messages": [{"role": "user", "content": demande}]},
        config={"recursion_limit": 2 * cfg.max_etapes + 5},
    )
    trace.evenement(
        "fin", statut=etat["statut"], reponse=etat.get("reponse", ""),
        etapes=etat.get("etapes", 0), appels_outils=etat.get("appels_outils", 0),
        tokens_entree=etat.get("tokens_entree", 0), tokens_sortie=etat.get("tokens_sortie", 0),
        duree_ms=round((time.perf_counter() - t0) * 1000),
    )
    return etat
