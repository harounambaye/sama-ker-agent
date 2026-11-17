"""Évaluation de l'agent Sama Kër Immobilier sur le jeu de 15 emails (exercice 6).

Lancement, depuis la racine du dépôt :
    python -m eval.evaluer --etiquette avant              # vrai agent (clé API nécessaire)
    python -m eval.evaluer --etiquette essai --simulation # sans API : teste le script lui-même
    python -m eval.evaluer --etiquette avant --limite 3   # seulement les 3 premiers emails

Pour chaque email, le script fait traiter le message par l'agent, compare le résultat
avec eval/emails_test.json et mesure : réussite, appels d'outils, tokens et temps.
Résultats : eval/resultats/<etiquette>.json (détail) et eval/resultats/<etiquette>.md (tableau).
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
FICHIER_EMAILS = DOSSIER / "emails_test.json"
DOSSIER_RESULTATS = DOSSIER / "resultats"

REFERENCE_BIEN = re.compile(r"SK-\d{3}")
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5}


# --------------------------------------------------------------------------- #
# 1. Faire traiter un email par l'agent                                       #
# --------------------------------------------------------------------------- #
# Chaque adaptateur renvoie un dictionnaire de la même forme :
#   decision          "repondre", "demander_precision", "transmettre", "creer_visite" ou None
#   reponse           texte du brouillon rédigé par l'agent ("" si aucun)
#   creneaux          liste de débuts de créneaux proposés, ISO 8601 (None si non fourni)
#   appels_outils, tokens_entree, tokens_sortie
# Quand le pipeline complet (exercice 5) sera fusionné, seul adaptateur_agent change.


def texte_de_l_email(email: dict) -> str:
    """Le message tel que l'agent le reçoit : expéditeur, objet et corps."""
    return f"De : {email['expediteur']}\nObjet : {email['objet']}\n\n{email['corps']}"


def adaptateur_agent():
    """Agent actuel (boucle de l'exercice 1) branché sur le catalogue."""
    from agent import config
    from agent.graphe import construire_graphe, executer
    from agent.outils import OutilsCatalogueLocal
    from agent.traces import Trace

    try:
        from mcp_server.catalogue import CatalogueSQLite as Catalogue
    except ImportError:  # catalogue réel pas encore fusionné dans cette branche
        from agent.catalogue_factice import CatalogueFactice as Catalogue

    cfg = config.charger()

    def traiter(email: dict) -> dict:
        trace = Trace(cfg.traces_dir, etiquette=f"eval-{email['id']}", verbeux=False)
        graphe = construire_graphe(cfg, OutilsCatalogueLocal(Catalogue()), trace)
        etat = executer(graphe, cfg, texte_de_l_email(email), trace)
        return {
            "decision": None,  # pas encore produit par l'agent de l'exercice 1
            "reponse": etat.get("reponse", ""),
            "creneaux": None,  # pas encore produit par l'agent de l'exercice 1
            "appels_outils": etat.get("appels_outils", 0),
            "tokens_entree": etat.get("tokens_entree", 0),
            "tokens_sortie": etat.get("tokens_sortie", 0),
        }

    return traiter


def adaptateur_simulation():
    """Faux agent qui renvoie exactement le résultat attendu, sans appeler l'API.
    Sert uniquement à vérifier que le script fonctionne : il doit obtenir 100 %."""

    def traiter(email: dict) -> dict:
        attendu = email["attendu"]
        mots = " ".join(attendu.get("doit_contenir", []))
        reponse = f"Biens proposés : {' '.join(attendu['biens_attendus'])}. {mots}".strip()
        creneaux = None
        if attendu.get("creneaux") and attendu["creneaux"]["jour"] in JOURS:
            c = attendu["creneaux"]
            jour = 9 + JOURS[c["jour"]]  # le 9 novembre 2026 est un lundi
            heures = [h for h in range(int(c["debut"][:2]), int(c["fin"][:2]))
                      if f"{h:02d}:00" != c.get("exclure")]
            creneaux = [f"2026-11-{jour:02d}T{h:02d}:00:00+00:00" for h in heures[: c["nombre"]]]
        return {
            "decision": attendu["decision"],
            "reponse": reponse,
            "creneaux": creneaux,
            "appels_outils": 1,
            "tokens_entree": 0,
            "tokens_sortie": 0,
        }

    return traiter


# --------------------------------------------------------------------------- #
# 2. Comparer le résultat avec l'attendu                                      #
# --------------------------------------------------------------------------- #


def sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


def verifier(attendu: dict, resultat: dict) -> list[str]:
    """Renvoie la liste des problèmes ; une liste vide veut dire « réussi »."""
    problemes = []
    reponse = resultat["reponse"]
    cites = set(REFERENCE_BIEN.findall(reponse))

    if resultat["decision"] is not None and resultat["decision"] != attendu["decision"]:
        problemes.append(f"décision {resultat['decision']} au lieu de {attendu['decision']}")

    if manquants := set(attendu["biens_attendus"]) - cites:
        problemes.append(f"biens attendus absents : {sorted(manquants)}")
    if interdits := set(attendu["biens_interdits"]) & cites:
        problemes.append(f"biens interdits proposés : {sorted(interdits)}")
    if attendu["decision"] in ("transmettre", "demander_precision") and cites:
        problemes.append(f"biens proposés alors qu'il fallait {attendu['decision']} : {sorted(cites)}")

    for mot in attendu.get("doit_contenir", []):
        if sans_accents(mot) not in sans_accents(reponse):
            problemes.append(f"la réponse ne contient pas « {mot} »")

    creneaux_attendus = attendu.get("creneaux")
    if creneaux_attendus and resultat["creneaux"] is not None:
        problemes += verifier_creneaux(creneaux_attendus, resultat["creneaux"])
    return problemes


def verifier_creneaux(attendu: dict, creneaux: list[str]) -> list[str]:
    problemes = []
    if len(creneaux) != attendu["nombre"]:
        problemes.append(f"{len(creneaux)} créneaux proposés au lieu de {attendu['nombre']}")
    for debut in creneaux:
        moment = datetime.fromisoformat(debut)
        heure = moment.strftime("%H:%M")
        if attendu["jour"] in JOURS and moment.weekday() != JOURS[attendu["jour"]]:
            problemes.append(f"créneau {debut} : pas un {attendu['jour']}")
        if not attendu["debut"] <= heure < attendu["fin"]:
            problemes.append(f"créneau {debut} : hors de la plage {attendu['debut']}-{attendu['fin']}")
        if attendu.get("exclure") == heure:
            problemes.append(f"créneau {debut} : c'est le créneau déjà pris")
    return problemes


# --------------------------------------------------------------------------- #
# 3. Rejouer le jeu de test et écrire les résultats                           #
# --------------------------------------------------------------------------- #


def evaluer(traiter, emails: list[dict]) -> list[dict]:
    lignes = []
    for email in emails:
        debut = time.perf_counter()
        try:
            resultat = traiter(email)
            problemes = verifier(email["attendu"], resultat)
        except Exception as exc:  # une panne sur un email ne doit pas arrêter l'évaluation
            resultat = {"decision": None, "reponse": "", "creneaux": None,
                        "appels_outils": 0, "tokens_entree": 0, "tokens_sortie": 0}
            problemes = [f"erreur pendant le traitement : {type(exc).__name__}: {exc}"]
        duree = time.perf_counter() - debut
        lignes.append({
            "id": email["id"],
            "categorie": email["categorie"],
            "reussi": not problemes,
            "problemes": problemes,
            "decision": resultat["decision"],
            "appels_outils": resultat["appels_outils"],
            "tokens": resultat["tokens_entree"] + resultat["tokens_sortie"],
            "duree_s": round(duree, 2),
            "reponse": resultat["reponse"],
        })
        print(f"{'OK' if not problemes else 'KO'}  {email['id']}  {email['categorie']}")
        for pb in problemes:
            print(f"      ! {pb}")
    return lignes


def resume(lignes: list[dict]) -> dict:
    n = len(lignes)
    return {
        "emails": n,
        "reussis": sum(l["reussi"] for l in lignes),
        "taux_reussite": round(100 * sum(l["reussi"] for l in lignes) / n, 1) if n else 0.0,
        "appels_outils_moyen": round(sum(l["appels_outils"] for l in lignes) / n, 1) if n else 0.0,
        "tokens_moyen": round(sum(l["tokens"] for l in lignes) / n) if n else 0,
        "duree_moyenne_s": round(sum(l["duree_s"] for l in lignes) / n, 2) if n else 0.0,
    }


def tableau_markdown(etiquette: str, lignes: list[dict], bilan: dict) -> str:
    texte = [
        f"# Évaluation « {etiquette} »",
        "",
        f"Taux de réussite : **{bilan['taux_reussite']} %** ({bilan['reussis']}/{bilan['emails']}) · "
        f"appels d'outils moyens : {bilan['appels_outils_moyen']} · "
        f"tokens moyens : {bilan['tokens_moyen']} · temps moyen : {bilan['duree_moyenne_s']} s",
        "",
        "| Email | Catégorie | Résultat | Appels d'outils | Tokens | Temps (s) | Problèmes |",
        "|---|---|---|---|---|---|---|",
    ]
    for l in lignes:
        texte.append(
            f"| {l['id']} | {l['categorie']} | {'OK' if l['reussi'] else 'KO'} | "
            f"{l['appels_outils']} | {l['tokens']} | {l['duree_s']} | {'; '.join(l['problemes']) or '-'} |"
        )
    return "\n".join(texte) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue l'agent sur le jeu de 15 emails.")
    parser.add_argument("--etiquette", required=True, help="nom de l'évaluation, ex. avant ou apres")
    parser.add_argument("--simulation", action="store_true", help="faux agent, sans appel à l'API")
    parser.add_argument("--limite", type=int, help="n'évaluer que les N premiers emails")
    args = parser.parse_args()

    emails = json.loads(FICHIER_EMAILS.read_text(encoding="utf-8"))["emails"]
    if args.limite:
        emails = emails[: args.limite]

    traiter = adaptateur_simulation() if args.simulation else adaptateur_agent()
    lignes = evaluer(traiter, emails)
    bilan = resume(lignes)

    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    (DOSSIER_RESULTATS / f"{args.etiquette}.json").write_text(
        json.dumps({"etiquette": args.etiquette, "bilan": bilan, "emails": lignes},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOSSIER_RESULTATS / f"{args.etiquette}.md").write_text(
        tableau_markdown(args.etiquette, lignes, bilan), encoding="utf-8"
    )
    print(f"\nTaux de réussite : {bilan['taux_reussite']} % ({bilan['reussis']}/{bilan['emails']})")
    print(f"Résultats écrits dans {DOSSIER_RESULTATS / args.etiquette}.json et .md")


if __name__ == "__main__":
    main()