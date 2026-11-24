"""Lecture des traces pour l'observation : parcours d'un fil dans le graphe, mesures,
écritures validées, et dessin du graphe (DOT) avec le chemin réellement suivi.

Aucune dépendance d'affichage : le poste du conseiller (poste_conseiller.py) et les
tests utilisent les mêmes fonctions.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

# Traces lues : celles du poste (ligne de commande et navigateur). Les traces de
# l'évaluation (eval-E01…) ont leurs propres fils factices et sont ignorées.
ETIQUETTES = ("pipeline", "poste")

LIBELLES = {
    "__start__": "Email reçu",
    "trier": "Tri\n(modèle)",
    "rechercher": "Recherche\ncatalogue ∥ agenda",
    "rediger": "Rédaction\n(modèle)",
    "preparer": "Brouillon\ndans le fil Gmail",
    "choisir_visite": "Choix du créneau\n(code)",
    "valider": "⏸ Validation\ndu conseiller",
    "ecrire": "Écriture\nGmail / Calendar",
    "suite_visite": "Suite de la visite\n(confirmation)",
    "transmettre": "Transmis à\nun conseiller",
    "refuser": "Refusé par\nle conseiller",
    "__end__": "Fin",
}

# L'événement d'écriture porte le type de la proposition exécutée.
TYPES_ECRITURE = ("envoyer_brouillon", "creer_visite", "deplacer_visite", "annuler_visite")


def charger_evenements(dossier: str | Path, etiquettes=ETIQUETTES) -> list[dict]:
    """Tous les événements des traces du poste, dans l'ordre chronologique. Chaque
    événement reçoit `instant` (datetime) : heure du fichier + t_ms."""
    evenements = []
    for chemin in Path(dossier).glob("*.jsonl"):
        morceaux = chemin.stem.split("_")
        if len(morceaux) < 3 or morceaux[1] not in etiquettes:
            continue
        try:
            debut = datetime.strptime(morceaux[0], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(ligne)
            except json.JSONDecodeError:
                continue  # ligne en cours d'écriture
            e["instant"] = debut + timedelta(milliseconds=e.get("t_ms", 0))
            e["fichier"] = chemin.name
            evenements.append(e)
    return sorted(evenements, key=lambda e: e["instant"])


def du_fil(evenements: list[dict], fil_id: str) -> list[dict]:
    return [e for e in evenements if e.get("fil_id") == fil_id]


def dernier_parcours(evenements_fil: list[dict]) -> list[tuple[str, str]]:
    """(nœud, statut) du dernier email du fil : depuis le dernier passage par « trier »,
    reprises après validation comprises."""
    noeuds = [(e["noeud"], e["statut"]) for e in evenements_fil if e["type"] == "noeud"]
    debuts = [i for i, (n, _) in enumerate(noeuds) if n == "trier"]
    return noeuds[debuts[-1]:] if debuts else noeuds


def mesures(evenements_fil: list[dict]) -> dict:
    """Coût et durée cumulés du fil : appels au modèle, tokens (cache compris), temps
    passé dans les nœuds (hors attente du conseiller)."""
    appels = [e for e in evenements_fil if e["type"] == "appel_modele"]
    return {
        "appels_modele": len(appels),
        "tokens_entree": sum(e.get("tokens_entree", 0) + e.get("tokens_cache_lus", 0)
                             + e.get("tokens_cache_ecrits", 0) for e in appels),
        "tokens_cache_lus": sum(e.get("tokens_cache_lus", 0) for e in appels),
        "tokens_sortie": sum(e.get("tokens_sortie", 0) for e in appels),
        "duree_ms": sum(e.get("duree_ms", 0) for e in evenements_fil if e["type"] == "noeud"),
    }


def ecritures(evenements: list[dict]) -> list[dict]:
    """Écritures exécutées après validation (envois, visites), tous fils confondus."""
    lignes = []
    for e in evenements:
        if e["type"] not in TYPES_ECRITURE:
            continue
        r = e.get("resultat") or {}
        lignes.append({
            "heure": e["instant"].strftime("%d/%m %H:%M:%S"),
            "fil": e.get("fil_id"),
            "écriture": e["type"],
            "conseiller": e.get("conseiller"),
            "résultat": "ok" if r.get("ok") else f"{r.get('code')} : {r.get('message')}",
        })
    return lignes


def dot(aretes: list[tuple[str, str]], parcours: list[tuple[str, str]]) -> str:
    """Graphe Graphviz : nœuds traversés en vert, pause en orange, transmission en gris,
    flèches du chemin suivi en gras. `aretes` vient de graphe.get_graph()."""
    suivis = [n for n, _ in parcours]
    chemin = ["__start__"] + [n for i, n in enumerate(suivis) if i == 0 or n != suivis[i - 1]]
    en_pause = parcours[-1][0] if parcours and parcours[-1][1] == "pause" else None
    if parcours and not en_pause:
        chemin.append("__end__")
    pris = set(zip(chemin, chemin[1:]))

    noeuds = list(dict.fromkeys([a for a, _ in aretes] + [b for _, b in aretes]))
    lignes = ['digraph G {', '  rankdir=TB; bgcolor="transparent";',
              '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 '
              'fillcolor="#ffffff" color="#9ca3af" fontcolor="#6b7280"];',
              '  edge [color="#d1d5db" arrowsize=0.7];']
    for n in noeuds:
        style = ""
        if n == en_pause:
            style = ' fillcolor="#fed7aa" color="#ea580c" fontcolor="#7c2d12" penwidth=2.5'
        elif n in chemin and n in ("transmettre", "refuser"):
            style = ' fillcolor="#e5e7eb" color="#4b5563" fontcolor="#111827" penwidth=2'
        elif n in chemin:
            style = ' fillcolor="#d1fae5" color="#059669" fontcolor="#064e3b" penwidth=2'
        forme = ' shape=ellipse' if n in ("__start__", "__end__") else ""
        libelle = LIBELLES.get(n, n).replace("\n", "\\n")
        lignes.append(f'  "{n}" [label="{libelle}"{forme}{style}];')
    for a, b in dict.fromkeys(aretes):
        style = ' color="#059669" penwidth=2.5' if (a, b) in pris else ""
        lignes.append(f'  "{a}" -> "{b}" [{style.strip()}];')
    lignes.append("}")
    return "\n".join(lignes)


def aretes_du_graphe(graphe) -> list[tuple[str, str]]:
    """Arêtes du graphe compilé, sans boucle (valider -> valider)."""
    return [(e.source, e.target) for e in graphe.get_graph().edges if e.source != e.target]
