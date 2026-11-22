"""Recherche des faits d'une réponse : biens du catalogue ET créneaux libres, en parallèle.

Le code appelle les briques avec les critères extraits par le tri ; le modèle ne
rédigera qu'à partir de ces faits. Une brique en erreur ne fait pas tomber la
recherche : l'erreur est rapportée dans `erreurs` et le pipeline décide.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TypedDict

from agent.dates import DAKAR, Fenetre, elargir, fenetre
from agent.outils import BoiteAOutils
from agent.traces import Trace
from contracts import Agenda, Bien, Creneau

NOMBRE_CRENEAUX = 3


class Faits(TypedDict):
    biens: list[Bien]
    introuvables: list[str]     # références citées qui n'existent pas
    indisponibles: list[str]    # références qui existent mais ne sont plus libres
    creneaux: list[Creneau]
    fenetre: str                # libellé de la période cherchée
    ajustements: list[str]      # écarts avec la demande, à expliquer au client
    erreurs: dict[str, dict]    # brique -> erreur au format commun


def choisir(creneaux: list[Creneau], heure: str | None, n: int = NOMBRE_CRENEAUX) -> list[Creneau]:
    """n créneaux répartis sur la période (un par heure de début) ; l'heure précise
    demandée passe en premier si elle est libre."""
    par_debut: dict[str, Creneau] = {}
    for c in sorted(creneaux, key=lambda c: c["debut"]):
        par_debut.setdefault(c["debut"], c)
    uniques = list(par_debut.values())
    retenus: list[Creneau] = []
    if heure:
        retenus = [c for c in uniques if datetime.fromisoformat(c["debut"]).astimezone(DAKAR)
                   .strftime("%H:%M") == heure][:1]
    reste = [c for c in uniques if c not in retenus]
    places = n - len(retenus)
    if places > 0 and reste:
        if len(reste) <= places:
            retenus += reste
        else:  # indices répartis : premier, ..., dernier
            pas = (len(reste) - 1) / (places - 1) if places > 1 else 0
            retenus += [reste[round(i * pas)] for i in range(places)]
    return sorted(retenus, key=lambda c: c["debut"])


def _chercher_biens(besoin: dict, outils: BoiteAOutils, trace: Trace) -> dict:
    t0 = time.perf_counter()
    if besoin["references"]:
        biens, introuvables, indisponibles = [], [], []
        for ref in besoin["references"]:
            r = outils.appeler("detail_bien", {"bien_id": ref})
            if r.get("ok"):
                (biens if r["bien"]["disponible"] else indisponibles).append(
                    r["bien"] if r["bien"]["disponible"] else ref)
            elif r.get("code") == "INTROUVABLE":
                introuvables.append(ref)
            else:
                return {"erreur": r}
        resultat = {"biens": biens, "introuvables": introuvables, "indisponibles": indisponibles}
    else:
        criteres = {k: besoin[k] for k in ("type", "quartier", "loyer_max", "pieces")
                    if besoin.get(k) is not None}
        r = outils.appeler("rechercher_biens", criteres)
        resultat = ({"biens": r["biens"], "introuvables": [], "indisponibles": []}
                    if r.get("ok") else {"erreur": r})
    trace.evenement("recherche_biens", besoin=besoin, resultat=resultat,
                    duree_ms=round((time.perf_counter() - t0) * 1000))
    return resultat


def _chercher_creneaux(f: Fenetre, agenda: Agenda, trace: Trace) -> dict:
    t0 = time.perf_counter()
    ajustements = [f.ajustement] if f.ajustement else []
    r = agenda.lister_creneaux_libres(None, f.debut.isoformat(), f.fin.isoformat())
    if r.get("ok") and not r["creneaux"]:
        f = elargir(f)
        ajustements.append(f.ajustement)
        r = agenda.lister_creneaux_libres(None, f.debut.isoformat(), f.fin.isoformat())
    if not r.get("ok"):
        trace.evenement("recherche_creneaux", fenetre=f.libelle, erreur=r)
        return {"erreur": r, "fenetre": f.libelle, "ajustements": ajustements}
    retenus = choisir(r["creneaux"], f.heure)
    if f.heure and not any(datetime.fromisoformat(c["debut"]).astimezone(DAKAR)
                           .strftime("%H:%M") == f.heure for c in retenus):
        ajustements.append(f"le créneau de {f.heure.replace(':', ' h ')} n'est pas disponible")
    trace.evenement("recherche_creneaux", fenetre=f.libelle, libres=len(r["creneaux"]),
                    retenus=retenus, duree_ms=round((time.perf_counter() - t0) * 1000))
    return {"creneaux": retenus, "fenetre": f.libelle, "ajustements": ajustements}


def rassembler(analyse: dict, outils: BoiteAOutils, agenda: Agenda,
               maintenant: datetime, trace: Trace) -> Faits:
    """Catalogue et agenda interrogés en parallèle."""
    f = fenetre(analyse["disponibilites"], maintenant)
    with ThreadPoolExecutor(max_workers=2) as pool:
        biens = pool.submit(_chercher_biens, analyse["besoin"], outils, trace)
        creneaux = pool.submit(_chercher_creneaux, f, agenda, trace)
        b, c = biens.result(), creneaux.result()
    erreurs = {}
    if "erreur" in b:
        erreurs["catalogue"] = b["erreur"]
    if "erreur" in c:
        erreurs["calendar"] = c["erreur"]
    return {
        "biens": b.get("biens", []),
        "introuvables": b.get("introuvables", []),
        "indisponibles": b.get("indisponibles", []),
        "creneaux": c.get("creneaux", []),
        "fenetre": c["fenetre"],
        "ajustements": c["ajustements"],
        "erreurs": erreurs,
    }
