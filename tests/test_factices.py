import pytest

from agent.factices import AgendaFactice, MessagerieFactice

JEUDI_15H = "2026-11-19T15:00:00+00:00"
JEUDI_18H = "2026-11-19T18:00:00+00:00"


@pytest.fixture
def visite():
    return dict(conseiller="aminata", debut="2026-11-19T15:45:00+00:00", bien_id="SK-001",
                adresse="Rue MZ-12, Mermoz, Dakar", client_nom="Awa Ndiaye",
                client_email="awa@example.com", fil_id="fil-1")


# ----------------------------- agenda ----------------------------------- #

def test_visites_de_45_minutes_tous_les_quarts_d_heure_jusqu_a_18h():
    r = AgendaFactice().lister_creneaux_libres("aminata", JEUDI_15H, JEUDI_18H)
    assert [c["debut"][11:16] for c in r["creneaux"]] == [
        "15:00", "15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45", "17:00", "17:15"]
    assert r["creneaux"][-1]["fin"] == JEUDI_18H


def test_un_creneau_qui_chevauche_une_visite_n_est_pas_libre(visite):
    agenda = AgendaFactice()
    agenda.creer_visite(**visite)                       # 15:45 - 16:30
    r = agenda.lister_creneaux_libres("aminata", JEUDI_15H, JEUDI_18H)
    assert [c["debut"][11:16] for c in r["creneaux"]] == [
        "15:00", "16:30", "16:45", "17:00", "17:15"]


def test_pas_de_creneau_le_dimanche():
    r = AgendaFactice().lister_creneaux_libres(None, "2026-11-22T08:00:00+00:00",
                                               "2026-11-22T19:00:00+00:00")
    assert r == {"ok": True, "creneaux": []}


def test_tous_les_conseillers_si_aucun_n_est_precise():
    r = AgendaFactice().lister_creneaux_libres(None, JEUDI_15H, "2026-11-19T15:45:00+00:00")
    assert sorted(c["conseiller"] for c in r["creneaux"]) == ["aminata", "khady", "moussa"]


def test_meme_fil_meme_creneau_aucun_doublon(visite):
    a = AgendaFactice()
    premier, second = a.creer_visite(**visite), a.creer_visite(**visite)
    assert premier["evenement_id"] == second["evenement_id"]
    assert second["deja_existante"] is True
    assert len(a.evenements) == 1


def test_creneau_pris_par_un_autre_client(visite):
    a = AgendaFactice()
    a.creer_visite(**visite)
    r = a.creer_visite(**{**visite, "fil_id": "fil-2"})
    assert r["code"] == "CRENEAU_INDISPONIBLE"


def test_creneau_reserve_n_est_plus_propose(visite):
    a = AgendaFactice()
    a.creer_visite(**visite)
    debuts = [c["debut"][11:16] for c in
              a.lister_creneaux_libres("aminata", JEUDI_15H, JEUDI_18H)["creneaux"]]
    assert "15:45" not in debuts


@pytest.mark.parametrize("debut", ["2026-11-22T10:30:00+00:00",   # dimanche
                                   "2026-11-19T08:15:00+00:00",   # avant 9h
                                   "2026-11-19T17:30:00+00:00",   # finirait après 18h
                                   "2026-11-19T15:10:00+00:00"])  # hors grille
def test_hors_regles_de_l_agence(visite, debut):
    assert AgendaFactice().creer_visite(**{**visite, "debut": debut})["code"] == "CRENEAU_INDISPONIBLE"


def test_evenement_contient_adresse_et_conseiller(visite):
    a = AgendaFactice()
    ev_id = a.creer_visite(**visite)["evenement_id"]
    ev = a.evenements[ev_id]
    assert ev["adresse"] == visite["adresse"] and ev["conseiller"] == "aminata"


def test_deplacer_puis_annuler(visite):
    a = AgendaFactice()
    ev_id = a.creer_visite(**visite)["evenement_id"]
    assert a.deplacer_visite(ev_id, "2026-11-19T16:30:00+00:00") == {"ok": True}
    assert a.evenements[ev_id]["debut"].startswith("2026-11-19T16:30")
    assert a.annuler_visite(ev_id) == {"ok": True}
    assert a.annuler_visite(ev_id)["code"] == "INTROUVABLE"


# ---------------------------- messagerie -------------------------------- #

def test_brouillon_dans_le_fil_puis_envoi_unique():
    m = MessagerieFactice()
    d = m.recevoir("Awa <awa@example.com>", "Visite F3", "Bonjour")
    b = m.creer_brouillon(d["fil_id"], "Bonjour Awa")["brouillon_id"]
    assert m.envoyer_brouillon(b) == {"ok": True}
    assert m.envoyer_brouillon(b)["code"] == "INTROUVABLE"
    assert m.envoyes[0]["a"] == "Awa <awa@example.com>"
    assert m.envoyes[0]["sujet"] == "Re: Visite F3"


def test_lire_demandes_ne_rend_que_les_messages_a_traiter():
    m = MessagerieFactice()
    d1 = m.recevoir("A <a@example.com>", "s", "c")
    m.recevoir("B <b@example.com>", "s", "c")
    m.changer_libelle(d1["message_id"], "en_attente_validation")
    assert [d["expediteur"] for d in m.lire_demandes()["demandes"]] == ["B <b@example.com>"]


def test_etat_partage_entre_deux_processus(tmp_path):
    chemin = tmp_path / "messagerie.json"
    d = MessagerieFactice(chemin).recevoir("A <a@example.com>", "s", "c")
    assert MessagerieFactice(chemin).lire_demandes()["demandes"][0]["fil_id"] == d["fil_id"]


def test_panne_simulee():
    m, a = MessagerieFactice(), AgendaFactice()
    m.panne = a.panne = True
    assert m.verifier_etat()["code"] == a.verifier_etat()["code"] == "INDISPONIBLE"
    assert m.envoyer_brouillon("d0001")["code"] == "INDISPONIBLE"
