"""Observation : parcours d'un fil, mesures et dessin, lus depuis les vraies traces."""

import json

from agent.observation import (aretes_du_graphe, charger_evenements, dernier_parcours, dot,
                               du_fil, ecritures, mesures)
from agent.redaction import REPERE
from agent.traces import Trace
from tests.test_pipeline import F3_MERMOZ, Agence, email, json_modele, tri


def agence_tracee(cfg):
    agence = Agence(cfg)
    agence.graphe_trace.chemin = agence.graphe_trace.chemin.with_name(
        agence.graphe_trace.chemin.name.replace("_", "_poste_", 1))
    return agence


def test_parcours_et_mesures_d_un_fil_en_pause(cfg):
    agence = agence_tracee(cfg)
    d = agence.recevoir()
    agence.traiter(d, json_modele(tri(**F3_MERMOZ)), email(f"SK-001.\n\n{REPERE}"))
    ev = charger_evenements(cfg.traces_dir)
    fil = du_fil(ev, d["fil_id"])
    assert dernier_parcours(fil)[-1] == ("valider", "pause")
    m = mesures(fil)
    assert m["appels_modele"] == 2 and m["tokens_entree"] == 200

    dessin = dot(aretes_du_graphe(agence.graphe), dernier_parcours(fil))
    assert '"valider" [label="⏸ Validation\\ndu conseiller" fillcolor="#fed7aa"' in dessin
    assert '"trier" -> "rechercher" [color="#059669" penwidth=2.5]' in dessin
    assert '"trier" -> "transmettre" [];' in dessin          # branche non suivie


def test_apres_envoi_le_chemin_va_jusqu_a_la_fin_et_l_ecriture_est_listee(cfg):
    agence = agence_tracee(cfg)
    d = agence.recevoir()
    agence.traiter(d, json_modele(tri(**F3_MERMOZ)), email(f"SK-001.\n\n{REPERE}"))
    agence.decider(d["fil_id"])
    ev = charger_evenements(cfg.traces_dir)
    dessin = dot(aretes_du_graphe(agence.graphe), dernier_parcours(du_fil(ev, d["fil_id"])))
    assert '"ecrire" -> "__end__" [color="#059669" penwidth=2.5]' in dessin
    (e,) = ecritures(ev)
    assert e["écriture"] == "envoyer_brouillon" and e["conseiller"] == "Khady" and e["résultat"] == "ok"


def test_nouvel_email_sur_le_fil_le_parcours_repart_du_tri():
    fil = [{"type": "noeud", "noeud": n, "statut": "fini"}
           for n in ("trier", "rechercher", "rediger", "preparer", "valider", "ecrire", "trier",
                     "choisir_visite")]
    fil.append({"type": "noeud", "noeud": "valider", "statut": "pause"})
    assert [n for n, _ in dernier_parcours(fil)] == ["trier", "choisir_visite", "valider"]


def test_traces_de_l_evaluation_ignorees(tmp_path):
    for nom in ("20261124-100000_eval-E01_aaaa.jsonl", "20261124-100001_poste_bbbb.jsonl"):
        (tmp_path / nom).write_text(json.dumps({"t_ms": 1, "type": "x", "fil_id": "fil-m0001"})
                                    + "\n{ligne coupée", encoding="utf-8")
    ev = charger_evenements(tmp_path)
    assert [e["fichier"] for e in ev] == ["20261124-100001_poste_bbbb.jsonl"]
