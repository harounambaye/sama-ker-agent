"""Tableau de comparaison entre deux évaluations (exercice 6).

Lancement, depuis la racine du dépôt, après deux évaluations :
    python -m eval.evaluer --etiquette avant
    python -m eval.evaluer --etiquette apres
    python -m eval.comparer avant apres

Lit eval/resultats/avant.json et eval/resultats/apres.json, affiche le tableau
et l'écrit dans eval/resultats/comparaison.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DOSSIER_RESULTATS = Path(__file__).resolve().parent / "resultats"


def charger(etiquette: str) -> dict:
    chemin = DOSSIER_RESULTATS / f"{etiquette}.json"
    if not chemin.exists():
        raise SystemExit(f"Fichier introuvable : {chemin}. "
                         f"Lancer d'abord : python -m eval.evaluer --etiquette {etiquette}")
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecart(avant: float, apres: float, unite: str = "") -> str:
    """Écart signé, par exemple « +13.3 % » ou « -120 »."""
    difference = round(apres - avant, 2)
    signe = "+" if difference > 0 else ""
    return f"{signe}{difference}{unite}"


def comparer(avant: dict, apres: dict) -> str:
    a, b = avant["bilan"], apres["bilan"]
    lignes = [
        f"# Comparaison « {avant['etiquette']} » → « {apres['etiquette']} »",
        "",
        "## Bilan",
        "",
        f"| Mesure | {avant['etiquette']} | {apres['etiquette']} | Écart |",
        "|---|---|---|---|",
        f"| Taux de réussite | {a['taux_reussite']} % ({a['reussis']}/{a['emails']}) | "
        f"{b['taux_reussite']} % ({b['reussis']}/{b['emails']}) | "
        f"{ecart(a['taux_reussite'], b['taux_reussite'], ' points')} |",
        f"| Appels d'outils par email | {a['appels_outils_moyen']} | {b['appels_outils_moyen']} | "
        f"{ecart(a['appels_outils_moyen'], b['appels_outils_moyen'])} |",
        f"| Tokens par email | {a['tokens_moyen']} | {b['tokens_moyen']} | "
        f"{ecart(a['tokens_moyen'], b['tokens_moyen'])} |",
        f"| Temps par email (s) | {a['duree_moyenne_s']} | {b['duree_moyenne_s']} | "
        f"{ecart(a['duree_moyenne_s'], b['duree_moyenne_s'])} |",
        "",
        "## Par email",
        "",
        f"| Email | Catégorie | {avant['etiquette']} | {apres['etiquette']} | Évolution |",
        "|---|---|---|---|---|",
    ]
    resultats_apres = {e["id"]: e for e in apres["emails"]}
    for e in avant["emails"]:
        f = resultats_apres.get(e["id"])
        if f is None:
            continue
        avant_ok, apres_ok = e["reussi"], f["reussi"]
        if avant_ok == apres_ok:
            evolution = "="
        else:
            evolution = "corrigé" if apres_ok else "régression"
        lignes.append(
            f"| {e['id']} | {e['categorie']} | {'OK' if avant_ok else 'KO'} | "
            f"{'OK' if apres_ok else 'KO'} | {evolution} |"
        )
    return "\n".join(lignes) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare deux évaluations de l'agent.")
    parser.add_argument("avant", help="étiquette de la première évaluation, ex. avant")
    parser.add_argument("apres", help="étiquette de la seconde évaluation, ex. apres")
    args = parser.parse_args()

    tableau = comparer(charger(args.avant), charger(args.apres))
    sortie = DOSSIER_RESULTATS / "comparaison.md"
    sortie.write_text(tableau, encoding="utf-8")
    print(tableau)
    print(f"Tableau écrit dans {sortie}")


if __name__ == "__main__":
    main()