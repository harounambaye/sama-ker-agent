"""Poste du conseiller : traitement des emails et validation humaine en ligne de commande.

    python -m agent.conseiller releve                       # emails « à traiter » de la messagerie
    python -m agent.conseiller demande "Un F3 à Mermoz..." --de "Awa <awa@example.com>"
    python -m agent.conseiller attente
    python -m agent.conseiller valider --conseiller Khady

`releve` traite chaque email « à traiter » jusqu'à la pause de validation.
`demande` simule un email entrant (BRIQUES=factice uniquement) ; avec --fil, il
répond dans un fil existant (ex. le client choisit un créneau).
`valider` peut tourner dans un autre terminal, plus tard : l'état est conservé par
fil Gmail dans le checkpointer SQLite.
"""

from __future__ import annotations

import argparse
from typing import Callable

from agent import config
from agent.briques import agenda_et_messagerie, catalogue, sondes
from agent.conversation import decider, en_attente
from agent.etat import VerificateurEtat, bloquer_si_indisponible
from agent.memoire import ouvrir_checkpointer
from agent.pipeline import construire_pipeline, traiter
from agent.traces import Trace
from agent.validation import Decision


def assembler(cfg: config.Config, verbeux: bool = False):
    outils, brique = catalogue()
    agenda, messagerie = agenda_et_messagerie()
    verificateur = VerificateurEtat(sondes(cfg, brique, agenda, messagerie))
    bloquer_si_indisponible(verificateur)
    checkpointer = ouvrir_checkpointer(cfg.checkpoint_db)
    graphe = construire_pipeline(
        cfg, outils, agenda, messagerie, verificateur,
        Trace(cfg.traces_dir, etiquette="pipeline", verbeux=verbeux), checkpointer,
    )
    return graphe, checkpointer, messagerie


def afficher_resultat(fil_id: str, s: dict) -> None:
    if s["en_attente"]:
        afficher_attente(s["en_attente"])
    else:
        raison = s.get("raison") or s["etat"].get("incident") or s["etat"].get("note") or ""
        suite = f" ({raison})" if raison else ""
        print(f"\n=== Fil {fil_id} terminé sans écriture : {s['issue']}{suite}")


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
    sous.add_parser("releve", help="traiter les emails « à traiter » de la messagerie")
    d = sous.add_parser("demande", help="simuler un email entrant (messagerie factice)")
    d.add_argument("corps")
    d.add_argument("--de", default="Client Test <client@example.com>")
    d.add_argument("--sujet", default="Demande de visite")
    d.add_argument("--fil", help="répondre dans ce fil (ex. choix d'un créneau)")
    sous.add_parser("attente", help="lister les écritures en attente de validation")
    v = sous.add_parser("valider", help="décider des écritures en attente")
    v.add_argument("--conseiller", required=True, help="nom du conseiller qui valide")
    v.add_argument("--fil", help="ne traiter que ce fil")
    p.add_argument("-v", "--verbeux", action="store_true")
    args = p.parse_args()

    cfg = config.charger()
    graphe, checkpointer, messagerie = assembler(cfg, args.verbeux)

    if args.commande == "releve":
        r = messagerie.lire_demandes()
        if not r.get("ok"):
            raise SystemExit(f"Lecture des demandes impossible : [{r['code']}] {r['message']}")
        for demande in r["demandes"]:
            afficher_resultat(demande["fil_id"], traiter(graphe, demande))
        print(f"\n{len(r['demandes'])} email(s) traité(s). Validation : "
              "python -m agent.conseiller valider --conseiller <nom>")
        return

    if args.commande == "demande":
        if not hasattr(messagerie, "recevoir"):
            raise SystemExit("« demande » simule un email : BRIQUES=factice uniquement. "
                             "Avec Gmail, envoyer un vrai email puis lancer « releve ».")
        demande = messagerie.recevoir(args.de, args.sujet, args.corps, args.fil)
        afficher_resultat(demande["fil_id"], traiter(graphe, demande))
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
        if s["en_attente"] and s["en_attente"].get("incident"):
            print(f"Toujours en attente : {s['en_attente']['incident']}")
        elif s["en_attente"]:
            print("Étape suivante à valider :")
            afficher_attente(s["en_attente"])
        else:
            print(f"Fil {a['fil_id']} : {s['issue']}")


if __name__ == "__main__":
    main()
