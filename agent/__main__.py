"""Usage : python -m agent "un F3 à Mermoz à moins de 400 000 F" [-v]"""

from __future__ import annotations

import argparse

from agent import config
from agent.briques import sondes
from agent.catalogue_factice import CatalogueFactice
from agent.etat import VerificateurEtat, bloquer_si_indisponible
from agent.graphe import construire_graphe, executer
from agent.outils import OutilsCatalogueLocal
from agent.traces import Trace


def main() -> None:
    p = argparse.ArgumentParser(description="Agent Sama Kër — une demande en ligne de commande")
    p.add_argument("demande")
    p.add_argument("-v", "--verbeux", action="store_true", help="affiche chaque étape")
    args = p.parse_args()

    cfg = config.charger()
    catalogue = CatalogueFactice()
    bloquer_si_indisponible(VerificateurEtat(sondes(cfg, catalogue)))
    trace = Trace(cfg.traces_dir, verbeux=args.verbeux)
    graphe = construire_graphe(cfg, OutilsCatalogueLocal(catalogue), trace)
    etat = executer(graphe, cfg, args.demande, trace)

    print("\n" + etat.get("reponse", ""))
    print(f"\n[{etat['statut']} · {etat.get('etapes', 0)} étapes · "
          f"{etat.get('appels_outils', 0)} appels d'outils · "
          f"{etat.get('tokens_entree', 0)}+{etat.get('tokens_sortie', 0)} tokens · "
          f"trace : {trace.chemin}]")


if __name__ == "__main__":
    main()
