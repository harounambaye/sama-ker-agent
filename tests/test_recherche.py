"""Faits d'une réponse : catalogue et agenda interrogés en parallèle par le code."""

import threading
from datetime import datetime, timezone

from agent.catalogue_factice import CatalogueFactice
from agent.factices import AgendaFactice
from agent.outils import OutilsCatalogueLocal
from agent.recherche import choisir, rassembler
from agent.traces import Trace

MARDI = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)


def analyse(jour="samedi", plage="matin", heure=None, semaine_prochaine=False, **besoin):
    b = {"type": None, "quartier": None, "loyer_max": None, "pieces": None, "references": []}
    return {"besoin": b | besoin,
            "disponibilites": {"jour": jour, "plage": plage, "heure": heure,
                               "semaine_prochaine": semaine_prochaine}}


def faits(a, agenda=None, tmp_path=None):
    return rassembler(a, OutilsCatalogueLocal(CatalogueFactice()), agenda or AgendaFactice(),
                      MARDI, Trace(str(tmp_path or ".") + "/traces"))


def heures(f):
    return [c["debut"][11:16] for c in f["creneaux"]]


def test_biens_et_trois_creneaux_dans_la_plage(tmp_path):           # E01
    f = faits(analyse(type="appartement", quartier="Mermoz", pieces=3, loyer_max=400_000),
              tmp_path=tmp_path)
    assert [b["id"] for b in f["biens"]] == ["SK-001"]
    assert len(f["creneaux"]) == 3 and all("09:00" <= h < "12:00" for h in heures(f))
    assert all(c["debut"].startswith("2026-11-21") for c in f["creneaux"])
    assert f["fenetre"] == "samedi 21 novembre, matin" and f["erreurs"] == {}


def test_aucun_bien(tmp_path):                                       # E05
    f = faits(analyse(quartier="Mermoz", pieces=3, loyer_max=300_000), tmp_path=tmp_path)
    assert f["biens"] == []


def test_reference_inexistante(tmp_path):                            # E06
    f = faits(analyse(references=["SK-045"]), tmp_path=tmp_path)
    assert f["biens"] == [] and f["introuvables"] == ["SK-045"]


def test_reference_plus_disponible(tmp_path):
    f = faits(analyse(references=["SK-003"]), tmp_path=tmp_path)
    assert f["indisponibles"] == ["SK-003"] and f["biens"] == []


def test_heure_demandee_deja_prise_exclue_et_signalee(tmp_path):    # E07
    agenda = AgendaFactice()
    for conseiller in ("aminata", "moussa", "khady"):
        agenda.creer_visite(conseiller, "2026-11-24T10:00:00+00:00", "SK-008", "x", "X",
                            "x@example.com", f"autre-{conseiller}")
    f = faits(analyse("mardi", None, heure="10:00", semaine_prochaine=True, quartier="Point E"),
              agenda, tmp_path)
    assert len(f["creneaux"]) == 3 and "10:00" not in heures(f)
    assert any("10 h 00" in a for a in f["ajustements"])


def test_heure_demandee_libre_proposee_en_premier(tmp_path):
    f = faits(analyse("mardi", None, heure="10:00", semaine_prochaine=True, quartier="Point E"),
              tmp_path=tmp_path)
    assert "10:00" in heures(f) and f["ajustements"] == []


def test_journee_pleine_on_elargit(tmp_path):
    pleine = AgendaFactice()
    for i, debut in enumerate(["09:00", "09:45", "10:30", "11:15"]):
        for conseiller in ("aminata", "moussa", "khady"):
            pleine.creer_visite(conseiller, f"2026-11-21T{debut}:00+00:00", "SK-001", "x", "X",
                                "x@example.com", f"f{i}{conseiller}")
    f = faits(analyse(quartier="Mermoz"), pleine, tmp_path)
    assert f["creneaux"] and all(c["debut"] > "2026-11-21T12" for c in f["creneaux"])
    assert any("aucun créneau libre" in a for a in f["ajustements"])


def test_agenda_en_panne_rapporte_sans_lever(tmp_path):
    agenda = AgendaFactice()
    agenda.panne = True
    f = faits(analyse(quartier="Mermoz"), agenda, tmp_path)
    assert f["erreurs"]["calendar"]["code"] == "INDISPONIBLE" and f["creneaux"] == []
    assert f["biens"]                                   # le catalogue a répondu quand même


def test_catalogue_et_agenda_interroges_en_parallele(tmp_path):
    barriere = threading.Barrier(2, timeout=5)

    class Lent:                     # chacun attend l'autre : ne passe qu'en parallèle
        def __init__(self, brique):
            self.brique = brique

        def __getattr__(self, nom):
            fonction = getattr(self.brique, nom)
            if nom in ("appeler", "lister_creneaux_libres"):
                def attendre(*a, **k):
                    barriere.wait()
                    return fonction(*a, **k)
                return attendre
            return fonction

    f = rassembler(analyse(quartier="Mermoz"), Lent(OutilsCatalogueLocal(CatalogueFactice())),
                   Lent(AgendaFactice()), MARDI, Trace(str(tmp_path)))
    assert f["biens"] and f["creneaux"]


def test_choisir_repartit_et_deduplique():
    creneaux = [{"conseiller": c, "debut": f"2026-11-21T{h}:00+00:00", "fin": ""}
                for h in ("09:00", "09:15", "09:30", "09:45", "10:00") for c in ("aminata", "moussa")]
    retenus = choisir(creneaux, None)
    assert [c["debut"][11:16] for c in retenus] == ["09:00", "09:30", "10:00"]
    assert all(c["conseiller"] == "aminata" for c in retenus)
