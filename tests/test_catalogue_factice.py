import pytest

from agent.catalogue_factice import CatalogueFactice
from agent.outils import OutilsCatalogueLocal


@pytest.fixture
def catalogue():
    return CatalogueFactice()


def ids(resultat):
    return [b["id"] for b in resultat["biens"]]


@pytest.mark.parametrize("quartier", ["Sacré-Cœur", "Sacré-Coeur", "sacre coeur", "SACRÉ-CŒUR"])
def test_quartier_insensible_aux_accents_et_ligatures(catalogue, quartier):
    assert ids(catalogue.rechercher_biens(quartier=quartier, pieces=4)) == ["SK-007"]


def test_biens_indisponibles_exclus(catalogue):
    # SK-003 (Mermoz, F3, 300 000 F) n'est pas disponible
    assert ids(catalogue.rechercher_biens(quartier="Mermoz", pieces=3, loyer_max=300_000)) == []


def test_tri_par_loyer_croissant(catalogue):
    loyers = [b["loyer_fcfa"] for b in catalogue.rechercher_biens(quartier="Mermoz")["biens"]]
    assert loyers == sorted(loyers)


def test_aucun_bien_renvoie_une_liste_vide(catalogue):
    assert catalogue.rechercher_biens(quartier="Mermoz", pieces=5) == {"ok": True, "biens": []}


def test_argument_invalide(catalogue):
    r = catalogue.rechercher_biens(loyer_max=-1)
    assert r["ok"] is False and r["code"] == "ARGUMENT_INVALIDE"


def test_detail_bien_inconnu(catalogue):
    r = catalogue.detail_bien("SK-999")
    assert r["ok"] is False and r["code"] == "INTROUVABLE"


def test_outil_inconnu_et_mauvais_arguments_sans_exception(catalogue):
    outils = OutilsCatalogueLocal(catalogue)
    assert outils.appeler("supprimer_tout", {})["code"] == "ARGUMENT_INVALIDE"
    assert outils.appeler("rechercher_biens", {"ville": "Dakar"})["code"] == "ARGUMENT_INVALIDE"
