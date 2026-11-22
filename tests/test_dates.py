"""Disponibilités -> fenêtre réelle. Référence : mardi 17 novembre 2026, 10 h, Dakar (UTC+0)."""

from datetime import datetime, timezone

from agent.dates import elargir, fenetre, libelle_creneau

MARDI = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
SAMEDI_SOIR = datetime(2026, 11, 21, 19, 0, tzinfo=timezone.utc)


def dispo(jour=None, plage=None, heure=None, semaine_prochaine=False):
    return {"jour": jour, "plage": plage, "heure": heure, "semaine_prochaine": semaine_prochaine}


def hm(d):
    return d.strftime("%Y-%m-%d %H:%M")


def test_samedi_matin():                                   # E01
    f = fenetre(dispo("samedi", "matin"), MARDI)
    assert (hm(f.debut), hm(f.fin)) == ("2026-11-21 09:00", "2026-11-21 12:00")
    assert f.libelle == "samedi 21 novembre, matin"


def test_lundi_apres_midi():                               # E02
    f = fenetre(dispo("lundi", "apres_midi"), MARDI)
    assert (hm(f.debut), hm(f.fin)) == ("2026-11-23 14:00", "2026-11-23 18:00")


def test_meme_jour_que_la_reception_renvoie_a_la_semaine_suivante():
    f = fenetre(dispo("mardi"), MARDI)
    assert hm(f.debut) == "2026-11-24 09:00"


def test_mardi_prochain_heure_precise():                   # E07
    f = fenetre(dispo("mardi", heure="10:00", semaine_prochaine=True), MARDI)
    assert hm(f.debut) == "2026-11-24 09:00" and f.heure == "10:00"


def test_jeudi_prochain_depuis_un_mardi_est_dans_la_semaine_suivante():
    assert hm(fenetre(dispo("jeudi", semaine_prochaine=True), MARDI).debut) == "2026-11-26 09:00"


def test_cette_semaine_jamais_dans_le_passe():             # E03
    f = fenetre(dispo("semaine"), MARDI)
    assert hm(f.debut) == "2026-11-17 12:00"               # maintenant + 2 h
    assert hm(f.fin) == "2026-11-21 18:00"                 # samedi soir


def test_cette_semaine_reçue_samedi_soir_passe_a_la_suivante():
    f = fenetre(dispo("semaine"), SAMEDI_SOIR)
    assert f.ajustement and f.debut > SAMEDI_SOIR


def test_dimanche_ferme_lundi_propose():
    f = fenetre(dispo("dimanche", "matin"), MARDI)
    assert hm(f.debut) == "2026-11-23 09:00" and "dimanche" in f.ajustement


def test_demain_un_samedi_soir_donne_lundi():
    f = fenetre(dispo("demain"), SAMEDI_SOIR)
    assert hm(f.debut) == "2026-11-23 09:00"


def test_sans_disponibilite_sept_jours_a_partir_de_maintenant():
    f = fenetre(None, MARDI)
    assert hm(f.debut) == "2026-11-17 12:00" and hm(f.fin) == "2026-11-24 18:00"


def test_elargir_apres_la_fenetre():
    f = elargir(fenetre(dispo("samedi", "matin"), MARDI))
    assert hm(f.debut) == "2026-11-22 09:00" and f.ajustement


def test_libelle_creneau():
    assert libelle_creneau("2026-11-21T09:45:00+00:00") == "samedi 21 novembre à 9 h 45"
