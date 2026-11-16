import json

from agent.catalogue_factice import CatalogueFactice
from agent.graphe import MESSAGE_LIMITE, construire_graphe, executer
from agent.outils import OutilsCatalogueLocal
from agent.traces import Trace
from tests.conftest import FauxClient, appel_outil, message, texte


def lancer(cfg, reponses, demande="un F3 à Mermoz"):
    client = FauxClient(reponses)
    trace = Trace(cfg.traces_dir)
    graphe = construire_graphe(cfg, OutilsCatalogueLocal(CatalogueFactice()), trace, client)
    return executer(graphe, cfg, demande, trace), client, trace


def test_outils_en_parallele_puis_reponse(cfg):
    etat, client, _ = lancer(cfg, [
        message([appel_outil("t1", "rechercher_biens", {"quartier": "Mermoz", "pieces": 3}),
                 appel_outil("t2", "detail_bien", {"bien_id": "SK-999"})], "tool_use"),
        message([texte("Je vous propose SK-001.")], "end_turn"),
    ])
    assert etat["statut"] == "termine"
    assert etat["reponse"] == "Je vous propose SK-001."
    assert etat["appels_outils"] == 2 and etat["etapes"] == 2
    # les deux résultats repartent dans UN seul message, l'erreur marquée is_error
    resultats = client.requetes[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in resultats] == ["t1", "t2"]
    assert resultats[0]["is_error"] is False and resultats[1]["is_error"] is True
    assert json.loads(resultats[1]["content"])["code"] == "INTROUVABLE"


def test_boucle_bornee_par_le_nombre_d_etapes(cfg):
    sans_fin = [message([appel_outil(f"t{i}", "rechercher_biens", {})], "tool_use")
                for i in range(50)]
    etat, _, _ = lancer(cfg, sans_fin)
    assert etat["statut"] == "limite"
    assert etat["etapes"] == cfg.max_etapes
    assert etat["reponse"] == MESSAGE_LIMITE


def test_boucle_bornee_par_les_tokens(cfg):
    gourmand = [message([appel_outil(f"t{i}", "rechercher_biens", {})], "tool_use",
                        entree=20_000) for i in range(5)]
    etat, _, _ = lancer(cfg, gourmand)
    assert etat["statut"] == "limite" and etat["etapes"] == 2


def test_refus_du_modele_transmis_a_un_conseiller(cfg):
    etat, _, _ = lancer(cfg, [message([], "refusal")])
    assert etat["statut"] == "refus" and etat["reponse"] == MESSAGE_LIMITE


def test_trace_contient_arguments_et_resultats(cfg):
    _, _, trace = lancer(cfg, [
        message([appel_outil("t1", "rechercher_biens", {"quartier": "Ngor"})], "tool_use"),
        message([texte("SK-010")], "end_turn"),
    ])
    evenements = [json.loads(l) for l in trace.chemin.read_text(encoding="utf-8").splitlines()]
    types = [e["type"] for e in evenements]
    assert types == ["debut", "appel_modele", "appel_outil", "appel_modele", "fin"]
    outil = evenements[2]
    assert outil["arguments"] == {"quartier": "Ngor"}
    assert outil["resultat"]["biens"][0]["id"] == "SK-010"
