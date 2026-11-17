"""Poste du conseiller : validation humaine en ligne de commande.

    python -m agent.conseiller demande "Je cherche un F3 à Mermoz..." --de "Awa <awa@example.com>"
    python -m agent.conseiller attente
    python -m agent.conseiller valider --conseiller Khady

`demande` simule un email entrant (messagerie factice) et le traite jusqu'à la
pause de validation. `valider` peut tourner dans un autre terminal, plus tard :
l'état est conservé par fil Gmail dans le checkpointer SQLite.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Callable

from agent import config
from agent.briques import sondes
from agent.catalogue_factice import CatalogueFactice
from agent.conversation import construire_graphe_conversation, decider, demarrer, en_attente
from agent.etat import VerificateurEtat, bloquer_si_indisponible
from agent.factices import AgendaFactice, MessagerieFactice
from agent.memoire import ouvrir_checkpointer
from agent.outils import OutilsCatalogueLocal
from agent.traces import Trace
from agent.validation import Decision


def assembler(cfg: config.Config, verbeux: bool = False):
    dossier = Path(os.getenv("FACTICES_DIR", "data/factices"))
    catalogue = CatalogueFactice()
    messagerie = MessagerieFactice(dossier / "messagerie.json")
    agenda = AgendaFactice(dossier / "agenda.json")
    verificateur = VerificateurEtat(sondes(cfg, catalogue, agenda, messagerie))
    bloquer_si_indisponible(verificateur)
    checkpointer = ouvrir_checkpointer(cfg.checkpoint_db)
    graphe = construire_graphe_conversation(
        cfg, OutilsCatalogueLocal(catalogue), agenda, messagerie, verificateur,
        Trace(cfg.traces_dir, etiquette="conversation", verbeux=verbeux), checkpointer,
    )
    return graphe, checkpointer, messagerie


def afficher_attente(attente: dict) -> None:
    p = attente["proposition"]
    print(f"\n=== Fil {attente['fil_id']} · {p['type']} · {p['resume']}")
    if attente.get("incident"):
        print(f"!!! {attente['incident']}")
    if p.get("note"):
        print("--- note interne (jamais envoyée) ---\n" + p["note"])
    if p.get("texte"):
        print("--- email qui sera envoyé au client ---\n" + p["texte"] + "\n---------------------")
    else:
        print(f"arguments : {p['arguments']}")


def demander_decision(attente: dict, conseiller: str,
                      saisir: Callable[[str], str] = input) -> Decision | None:
    """o = approuver, m = modifier, n = refuser, p = passer (None)."""
    while True:
        choix = saisir("[o] approuver  [m] modifier  [n] refuser  [p] passer > ").strip().lower()
        if choix == "o":
            return {"action": "approuver", "conseiller": conseiller}
        if choix == "n":
            return {"action": "refuser", "conseiller": conseiller,
                    "motif": saisir("Motif du refus > ").strip()}
        if choix == "p":
            return None
        if choix == "m" and attente["proposition"]["type"] == "envoyer_brouillon":
            print("Nouveau texte, terminé par une ligne contenant seulement « . » :")
            lignes = []
            while (ligne := saisir("")) != ".":
                lignes.append(ligne)
            return {"action": "modifier", "conseiller": conseiller, "texte": "\n".join(lignes)}
        print("Choix invalide.")


def main() -> None:
    p = argparse.ArgumentParser(description="Poste du conseiller Sama Kër")
    sous = p.add_subparsers(dest="commande", required=True)
    d = sous.add_parser("demande", help="simuler un email entrant et le traiter")
    d.add_argument("corps")
    d.add_argument("--de", default="Client Test <client@example.com>")
    d.add_argument("--sujet", default="Demande de visite")
    sous.add_parser("attente", help="lister les écritures en attente de validation")
    v = sous.add_parser("valider", help="décider des écritures en attente")
    v.add_argument("--conseiller", required=True, help="nom du conseiller qui valide")
    v.add_argument("--fil", help="ne traiter que ce fil")
    p.add_argument("-v", "--verbeux", action="store_true")
    args = p.parse_args()

    cfg = config.charger()
    graphe, checkpointer, messagerie = assembler(cfg, args.verbeux)

    if args.commande == "demande":
        demande = messagerie.recevoir(args.de, args.sujet, args.corps)
        s = demarrer(graphe, cfg, demande)
        if s["en_attente"]:
            afficher_attente(s["en_attente"])
            print("\nEn attente de validation : python -m agent.conseiller valider --conseiller <nom>")
        else:
            print(f"Fil {demande['fil_id']} terminé sans écriture : {s['issue']}")
        return

    attentes = en_attente(graphe, checkpointer)
    if args.commande == "attente":
        for a in attentes:
            afficher_attente(a)
        print(f"\n{len(attentes)} écriture(s) en attente.")
        return

    for a in attentes:
        if args.fil and a["fil_id"] != args.fil:
            continue
        afficher_attente(a)
        decision = demander_decision(a, args.conseiller)
        if decision is None:
            continue
        s = decider(graphe, cfg, a["fil_id"], decision)
        if s["en_attente"]:
            print(f"Toujours en attente : {s['en_attente'].get('incident')}")
        else:
            print(f"Fil {a['fil_id']} : {s['issue']}")


if __name__ == "__main__":
    main()
