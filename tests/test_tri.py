"""Tri et extraction : appel unique au modèle, sortie typée, parcours décidé par le code."""

import json

import anthropic
import httpx
import pytest

from agent.modele import appeler
from agent.traces import Trace
from agent.tri import SCHEMA, analyser, criteres_suffisants, parcours
from tests.conftest import FauxClient, message, texte

DEMANDE = {"message_id": "m1", "fil_id": "f1", "expediteur": "Awa <awa@example.com>",
           "sujet": "F3 Mermoz", "corps": "Un F3 à Mermoz, 400k max, samedi matin ?",
           "recu_le": "2026-11-17T10:00:00+00:00"}


def analyse(categorie="demande_visite", manipulation=False, **besoin):
    b = {"type": None, "quartier": None, "loyer_max": None, "pieces": None, "references": []}
    b |= besoin
    return {"categorie": categorie, "motif": "m", "manipulation": manipulation,
            "nom_client": "Awa", "besoin": b, "numero_creneau": None,
            "disponibilites": {"jour": "samedi", "semaine_prochaine": False,
                               "plage": "matin", "heure": None}}


def json_modele(donnees):
    return message([texte(json.dumps(donnees))], "end_turn")


# ------------------------------------------------------------- appel typé --- #

def test_requete_sortie_typee_et_email_encadre(cfg):
    client = FauxClient([json_modele(analyse(quartier="Mermoz"))])
    r = analyser(client, cfg, DEMANDE, Trace(cfg.traces_dir))
    assert r["ok"] and r["analyse"]["besoin"]["quartier"] == "Mermoz"
    requete = client.requetes[0]
    assert requete["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert "tool_choice" not in requete and "tools" not in requete
    contenu = requete["messages"][0]["content"]
    assert contenu.startswith("<email>") and contenu.rstrip().endswith("</email>")
    assert "Reçu le : 2026-11-17" in contenu


def test_creneaux_deja_proposes_numerotes_pour_la_confirmation(cfg):
    client = FauxClient([json_modele(analyse("confirmation") | {"numero_creneau": 2})])
    r = analyser(client, cfg, DEMANDE, Trace(cfg.traces_dir),
                 ["samedi 21 novembre à 9 h 00", "samedi 21 novembre à 10 h 30"])
    assert r["analyse"]["numero_creneau"] == 2
    contenu = client.requetes[0]["messages"][0]["content"]
    assert "<creneaux_proposes>\n1. samedi 21 novembre à 9 h 00\n2. samedi" in contenu
    assert contenu.index("</email>") < contenu.index("<creneaux_proposes>")


def test_schema_strict_partout():
    """Sorties structurées : chaque objet ferme ses propriétés et les exige toutes."""
    def objets(s):
        if isinstance(s, dict):
            if s.get("type") == "object":
                yield s
            for v in s.values():
                yield from objets(v)
        elif isinstance(s, list):
            for v in s:
                yield from objets(v)
    for o in objets(SCHEMA):
        assert o["additionalProperties"] is False
        assert set(o["required"]) == set(o["properties"])


def test_normalisation_des_references_et_valeurs_absurdes(cfg):
    sortie = analyse(references=["sk-045 ", "SK-045"], loyer_max=0, pieces=-1, quartier="  ")
    r = analyser(FauxClient([json_modele(sortie)]), cfg, DEMANDE, Trace(cfg.traces_dir))
    b = r["analyse"]["besoin"]
    assert b["references"] == ["SK-045"]
    assert b["loyer_max"] is None and b["pieces"] is None and b["quartier"] is None


def test_json_illisible_erreur_interne(cfg):
    r = analyser(FauxClient([message([texte("pas du json")], "end_turn")]), cfg, DEMANDE,
                 Trace(cfg.traces_dir))
    assert r["ok"] is False and r["code"] == "INTERNE"


def test_refus_du_modele(cfg):
    r = analyser(FauxClient([message([texte("")], "refusal")]), cfg, DEMANDE, Trace(cfg.traces_dir))
    assert r["code"] == "AUTORISATION"


class ClientEnPanne(FauxClient):
    """Le modèle principal est surchargé ; le modèle de secours répond."""

    def create(self, **requete):
        self.requetes.append(requete)
        if requete["model"] == "modele-de-test":
            raise anthropic.InternalServerError(
                "surcharge", response=httpx.Response(529, request=httpx.Request("POST", "http://x")),
                body=None)
        return next(self._reponses)


def test_bascule_sur_le_modele_de_secours(cfg):
    from dataclasses import replace
    cfg2 = replace(cfg, model_secours="modele-secours")
    client = ClientEnPanne([message([texte("ok")], "end_turn")])
    r = appeler(client, cfg2, Trace(cfg.traces_dir), nom="t", systeme="s", contenu="c")
    assert r == {"ok": True, "texte": "ok", "tokens_entree": 100, "tokens_sortie": 20}
    assert [q["model"] for q in client.requetes] == ["modele-de-test", "modele-secours"]


def test_sans_secours_la_panne_est_signalee(cfg):
    r = appeler(ClientEnPanne([]), cfg, Trace(cfg.traces_dir), nom="t", systeme="s", contenu="c")
    assert r["code"] == "INDISPONIBLE"


# ------------------------------------------------- parcours décidé par le code --- #

@pytest.mark.parametrize("a, attendu", [
    (analyse("hors_perimetre"), "transmettre"),                       # E10, E11
    (analyse("injection", manipulation=True), "transmettre"),         # E12
    (analyse("question_agence"), "repondre_agence"),                  # E15
    (analyse("confirmation"), "confirmer"),
    (analyse(type="appartement"), "demander_precision"),              # E08 « pas trop cher »
    (analyse(), "demander_precision"),                                # E09 « faire une visite »
    (analyse(type="villa", quartier="Médina"), "proposer"),           # E04
    (analyse(references=["SK-045"]), "proposer"),                     # E06
    (analyse(type="appartement", pieces=3, loyer_max=400_000), "proposer"),
    (analyse(quartier="Ouakam", pieces=2, manipulation=True), "proposer"),  # E13
])
def test_parcours(a, attendu):
    assert parcours(a) == attendu


def test_criteres_suffisants():
    assert not criteres_suffisants(analyse(loyer_max=300_000)["besoin"])
    assert criteres_suffisants(analyse(quartier="Yoff")["besoin"])
