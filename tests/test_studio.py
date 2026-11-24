"""Graphe de LangGraph Studio : même pipeline, un fil Studio = un fil Gmail."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.catalogue_factice import CatalogueFactice
from agent.outils import OutilsCatalogueLocal
from agent.redaction import REPERE
from agent.studio import construire_studio
from tests.test_pipeline import F3_MERMOZ, Client, email, json_modele, tri

APPROUVER = {"action": "approuver", "conseiller": "Khady"}


def test_email_saisi_dans_studio_traite_valide_puis_reponse_dans_le_meme_fil(cfg, monkeypatch):
    monkeypatch.setattr("agent.studio.sondes", lambda cfg, brique, agenda, messagerie: {
        "gmail": messagerie.verifier_etat, "calendar": agenda.verifier_etat})
    catalogue = CatalogueFactice()
    client = Client([json_modele(tri(**F3_MERMOZ)), email(f"SK-001.\n\n{REPERE}")])
    g = construire_studio(cfg, OutilsCatalogueLocal(catalogue), catalogue, client, InMemorySaver())
    fil = {"configurable": {"thread_id": "studio-1"}}

    g.invoke({"expediteur": "Awa <awa@example.com>", "objet": "F3", "corps": "Un F3 à Mermoz"}, fil)
    etat = g.get_state(fil, subgraphs=True)
    (pause,) = etat.interrupts
    assert pause.value["proposition"]["type"] == "envoyer_brouillon"

    g.invoke(Command(resume=APPROUVER), fil)
    valeurs = g.get_state(fil).values
    assert valeurs["issue"] == "envoye" and len(valeurs["creneaux_proposes"]) == 3

    client.reponses.append(json_modele(tri("confirmation", numero=2)))
    g.invoke({"expediteur": "Awa <awa@example.com>", "objet": "Re: F3",
              "corps": "Le deuxième créneau"}, fil)
    (pause,) = g.get_state(fil, subgraphs=True).interrupts
    assert pause.value["proposition"]["type"] == "creer_visite"
    assert pause.value["fil_id"] == valeurs["fil_id"]          # même fil Gmail
