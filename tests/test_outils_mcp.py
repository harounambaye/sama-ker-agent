"""Client MCP de l'agent contre le vrai serveur du catalogue, en mémoire (sans processus)."""

import pytest

from agent.outils_mcp import OutilsMCP, _nettoyer_schema
from mcp_server import serveur as module_serveur
from mcp_server.creer_catalogue import creer_catalogue


@pytest.fixture(scope="module")
def outils(tmp_path_factory):
    base = tmp_path_factory.mktemp("catalogue") / "catalogue.sqlite"
    creer_catalogue(base)
    ancien = module_serveur.catalogue.chemin
    module_serveur.catalogue.chemin = base
    with OutilsMCP(module_serveur.serveur) as o:
        yield o
    module_serveur.catalogue.chemin = ancien


def test_le_modele_voit_les_outils_du_serveur_sauf_la_sonde(outils):
    noms = [d["name"] for d in outils.definitions()]
    assert noms == ["rechercher_biens", "detail_bien"]


def test_schemas_lisibles_pour_le_modele(outils):
    schema = {d["name"]: d["input_schema"] for d in outils.definitions()}["rechercher_biens"]
    assert schema["properties"]["pieces"]["type"] == "integer"
    assert "anyOf" not in schema["properties"]["type"]
    assert "title" not in schema


def test_recherche_au_format_du_contrat(outils):
    r = outils.appeler("rechercher_biens", {"quartier": "Mermoz", "pieces": 3, "loyer_max": 400_000})
    assert r["ok"] is True and [b["id"] for b in r["biens"]] == ["SK-001"]


def test_ligature_et_accents_cote_serveur(outils):
    ids = {b["id"] for b in outils.appeler("rechercher_biens", {"quartier": "sacre coeur"})["biens"]}
    assert "SK-007" in ids


def test_erreur_metier_du_serveur_transmise_telle_quelle(outils):
    r = outils.appeler("detail_bien", {"bien_id": "SK-099"})
    assert r == {"ok": False, "code": "INTROUVABLE", "message": r["message"]}


def test_argument_mal_type_devient_argument_invalide(outils):
    r = outils.appeler("rechercher_biens", {"pieces": "trois"})
    assert r["ok"] is False and r["code"] == "ARGUMENT_INVALIDE" and "pieces" in r["message"]


def test_outil_inconnu(outils):
    assert outils.appeler("supprimer_bien", {})["code"] == "ARGUMENT_INVALIDE"


def test_sonde_d_etat(outils):
    assert outils.verifier_etat()["ok"] is True


def test_serveur_injoignable_ni_exception_ni_bien_invente():
    with OutilsMCP("http://127.0.0.1:9/mcp", delai_s=5) as o:
        assert o.definitions() == []
        assert o.verifier_etat()["code"] == "INDISPONIBLE"
        r = o.appeler("rechercher_biens", {})
        assert r["code"] == "INDISPONIBLE" and "mémoire" in r["message"]


def test_nettoyer_schema_garde_les_types_reels():
    brut = {"title": "X", "type": "object", "properties": {
        "q": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Q"}}}
    assert _nettoyer_schema(brut) == {"type": "object", "properties": {"q": {"type": "string"}}}


def test_ressource_de_l_agence(outils):
    r = outils.lire_ressource("agence://informations")
    assert r["ok"] and "dimanche" in r["texte"] and "identité" in r["texte"]


def test_ressource_inconnue(outils):
    assert outils.lire_ressource("agence://inconnue")["ok"] is False
