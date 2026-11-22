"""Rédaction : le modèle écrit, le code insère les créneaux exacts et contrôle."""

import json

from agent.redaction import REPERE, SCHEMA, controler, inserer_creneaux, rediger
from agent.traces import Trace
from tests.conftest import FauxClient, message, texte

DEMANDE = {"message_id": "m1", "fil_id": "f1", "expediteur": "Awa <awa@example.com>",
           "sujet": "F3", "corps": "Un F3 à Mermoz ?", "recu_le": ""}
SK001 = {"id": "SK-001", "type": "appartement", "quartier": "Mermoz", "loyer_fcfa": 350_000,
         "pieces": 3, "adresse": "Rue MZ-12", "disponible": True, "description": ""}
CRENEAUX = [{"conseiller": "aminata", "debut": "2026-11-21T09:00:00+00:00", "fin": ""},
            {"conseiller": "khady", "debut": "2026-11-21T10:30:00+00:00", "fin": ""}]
EMAIL = f"Bonjour Awa,\n\nNous avons SK-001.\n\n{REPERE}\n\nCordialement,\nSama Kër Immobilier"


def sortie(email=EMAIL, note=""):
    return message([texte(json.dumps({"email_client": email, "note_conseiller": note}))], "end_turn")


def test_creneaux_inseres_par_le_code(cfg):
    client = FauxClient([sortie(note="RAS")])
    r = rediger(client, cfg, Trace(cfg.traces_dir), cas="proposer", demande=DEMANDE,
                faits={"biens": [SK001]}, creneaux=CRENEAUX)
    assert r["ok"] and REPERE not in r["email"]
    assert "- samedi 21 novembre à 9 h 00, avec Aminata Diop" in r["email"]
    assert "- samedi 21 novembre à 10 h 30, avec Khady Sarr" in r["email"]
    assert r["note"] == "RAS"
    requete = client.requetes[0]
    assert requete["output_config"]["format"]["schema"] == SCHEMA
    faits = requete["messages"][0]["content"].split("<faits>")[1]
    assert "2026-11-21" not in faits          # le modèle ne voit pas les dates exactes


def test_reference_inventee_refusee(cfg):
    r = rediger(FauxClient([sortie("Bonjour, voici SK-001 et SK-099.")]), cfg,
                Trace(cfg.traces_dir), cas="proposer", demande=DEMANDE, faits={"biens": [SK001]})
    assert r["ok"] is False and "SK-099" in r["message"]


def test_reference_introuvable_peut_etre_citee(cfg):
    r = rediger(FauxClient([sortie("Bonjour, l'annonce SK-045 n'existe pas.")]), cfg,
                Trace(cfg.traces_dir), cas="proposer", demande=DEMANDE,
                faits={"biens": [], "introuvables": ["SK-045"]})
    assert r["ok"]


def test_sans_creneau_le_repere_disparait(cfg):
    r = rediger(FauxClient([sortie()]), cfg, Trace(cfg.traces_dir), cas="demander_precision",
                demande=DEMANDE, faits={"biens": [SK001]})
    assert REPERE not in r["email"]


def test_repere_oublie_liste_placee_avant_la_signature():
    email = inserer_creneaux("Bonjour,\n\nVoici nos dates.\n\nCordialement,\nSama Kër", CRENEAUX)
    assert email.index("9 h 00") < email.index("Cordialement")


def test_controle_mise_en_forme():
    assert "Markdown" in controler("**Référence** SK-001", {"SK-001"})
    assert "Objet" in controler("Objet : Re: visite\nBonjour", set())
    assert controler("Bonjour, SK-001.", {"SK-001"}) is None


def test_note_sans_phrase_sur_la_mecanique():
    from agent.redaction import nettoyer_note
    note = ("Le client choisit le 2e créneau. Vérifier que le repère [CRENEAUX] est remplacé "
            "par la date retenue. Bien disponible.")
    assert nettoyer_note(note) == "Le client choisit le 2e créneau. Bien disponible."
