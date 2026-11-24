"""Le pipeline dans LangGraph Studio : voir le graphe s'exécuter nœud par nœud.

    langgraph dev        # depuis la racine du dépôt (langgraph.json), puis le lien Studio

Studio est fourni par LangSmith : il faut un compte LangSmith. Un fil Studio
correspond à un fil Gmail :
- entrée : {"expediteur", "objet", "corps"} ;
- pause de validation : reprendre avec {"action": "approuver", "conseiller": "Khady"} ;
- réponse du client : nouvelle entrée dans le même fil Studio.

Le graphe est le même que celui du poste, précédé du nœud `recevoir`, qui dépose
l'email dans une messagerie factice en mémoire. Gmail et Calendar sont factices
et le catalogue suit CATALOGUE. Rien n'est envoyé à un vrai client.
"""

from __future__ import annotations

from typing import TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from agent import config
from agent.briques import catalogue, sondes
from agent.etat import VerificateurEtat
from agent.factices import AgendaFactice, MessagerieFactice
from agent.pipeline import EtatPipeline, construire_pipeline
from agent.traces import Trace


class EntreeStudio(TypedDict):
    expediteur: str
    objet: str
    corps: str


class EtatStudio(EtatPipeline, total=False):
    objet: str
    corps: str


def construire_studio(cfg: config.Config, outils, brique, client: anthropic.Anthropic | None = None,
                      checkpointer=None):
    agenda, messagerie = AgendaFactice(), MessagerieFactice()
    verificateur = VerificateurEtat(sondes(cfg, brique, agenda, messagerie))
    # Sans checkpointer propre : le sous-graphe utilise celui de Studio (ou du parent).
    pipeline = construire_pipeline(cfg, outils, agenda, messagerie, verificateur,
                                   Trace(cfg.traces_dir, etiquette="studio"), None, client)

    def recevoir(etat: EtatStudio) -> dict:
        """L'email saisi arrive dans la messagerie factice ; dans un fil déjà commencé,
        c'est la réponse du client dans ce même fil."""
        demande = messagerie.recevoir(etat["expediteur"], etat["objet"], etat["corps"],
                                      etat.get("fil_id"))
        return {"demande": demande, "fil_id": demande["fil_id"],
                "message_id": demande["message_id"], "expediteur": demande["expediteur"],
                "analyse": None, "parcours": None, "decision_agent": None, "note": "",
                "faits": None, "brouillon_texte": None, "proposition": None, "decision": None,
                "incident": None, "issue": None, "tokens_entree": 0, "tokens_sortie": 0,
                "appels_modele": 0, "appels_outils": 0}

    g = StateGraph(EtatStudio, input_schema=EntreeStudio)
    g.add_node("recevoir", recevoir)
    g.add_node("pipeline", pipeline)
    g.add_edge(START, "recevoir")
    g.add_edge("recevoir", "pipeline")
    g.add_edge("pipeline", END)
    return g.compile(checkpointer=checkpointer)


def graphe():
    """Point d'entrée déclaré dans langgraph.json."""
    outils, brique = catalogue()
    return construire_studio(config.charger(), outils, brique)
