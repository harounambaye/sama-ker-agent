"""Critère d'acceptation de l'exercice 1, en une commande :

    python -m agent.critere_ex1 [-v]

Sur dix demandes, vérifie que l'agent :
  1. ne cite que des biens renvoyés par un outil pendant CE traitement (ancrage) ;
  2. cite les biens attendus quand il y en a ;
  3. dit clairement « aucun bien » quand rien ne correspond.

Les résultats attendus correspondent au catalogue factice ; ils seront recalés
sur la base de Fatou à l'exercice 2. Le contrôle d'ancrage (1) reste valable tel quel.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from agent import config
from agent.catalogue_factice import CatalogueFactice
from agent.graphe import construire_graphe, executer
from agent.outils import OutilsCatalogueLocal
from agent.traces import Trace

DEMANDES: list[tuple[str, set[str]]] = [
    ("Bonjour, je cherche un F3 à Mermoz à moins de 400 000 F.", {"SK-001"}),
    ("Un F3 à Mermoz à moins de 300 000 F, c'est possible ?", set()),
    ("Avez-vous un studio au Plateau ?", {"SK-005"}),
    ("Je veux une villa aux Almadies, budget 1 million par mois.", set()),
    ("Un F2 à Ouakam pour moins de 300 000 F.", {"SK-006"}),
    ("Je cherche un F4 à Sacré-Coeur.", {"SK-007"}),
    ("Appartement 3 pièces au Point E, maximum 400k.", {"SK-008"}),
    ("Une chambre à Yoff svp.", {"SK-009"}),
    ("Un F5 à Mermoz ?", set()),
    ("F2 à Ngor, budget 350 000 F max.", {"SK-010"}),
]

REF = re.compile(r"SK-\d{3}")
AUCUN = re.compile(r"aucun(e)?\s+(bien|logement|appartement|studio|villa|chambre|r[ée]sultat)", re.I)


def ids_renvoyes_par_outils(messages: list[dict]) -> set[str]:
    ids: set[str] = set()
    for m in messages:
        if m["role"] != "user" or not isinstance(m["content"], list):
            continue
        for bloc in m["content"]:
            if bloc.get("type") == "tool_result":
                ids |= set(REF.findall(bloc["content"]))
    return ids


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-v", "--verbeux", action="store_true")
    args = p.parse_args()

    cfg = config.charger()
    reussites = 0
    for i, (demande, attendus) in enumerate(DEMANDES, 1):
        trace = Trace(cfg.traces_dir, etiquette=f"ex1-{i:02d}", verbeux=args.verbeux)
        graphe = construire_graphe(cfg, OutilsCatalogueLocal(CatalogueFactice()), trace)
        etat = executer(graphe, cfg, demande, trace)
        reponse = etat.get("reponse", "")

        cites = set(REF.findall(reponse))
        vus = ids_renvoyes_par_outils(etat["messages"])
        problemes = []
        if etat["statut"] != "termine":
            problemes.append(f"statut {etat['statut']}")
        if hors_outils := cites - vus:
            problemes.append(f"biens cités sans résultat d'outil : {sorted(hors_outils)}")
        if manquants := attendus - cites:
            problemes.append(f"biens attendus absents : {sorted(manquants)}")
        if not attendus and not AUCUN.search(reponse):
            problemes.append("n'indique pas clairement qu'aucun bien ne correspond")

        ok = not problemes
        reussites += ok
        print(f"{'OK ' if ok else 'KO '} {i:02d}. {demande}")
        print(f"     cités={sorted(cites) or '-'} attendus={sorted(attendus) or 'aucun'} "
              f"· {etat.get('appels_outils', 0)} outils · {etat.get('etapes', 0)} étapes")
        for pb in problemes:
            print(f"     ! {pb}")
        if args.verbeux or not ok:
            print("     " + reponse.replace("\n", "\n     "))

    print(f"\n{reussites}/{len(DEMANDES)} demandes conformes.")
    sys.exit(0 if reussites == len(DEMANDES) else 1)


if __name__ == "__main__":
    main()
