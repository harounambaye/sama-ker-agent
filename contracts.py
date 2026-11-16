"""Contrats d'interface partagés — Sama Kër Immobilier.

Figés par le Lead Tech. Toute modification passe par une pull request du Lead Tech,
annoncée à l'équipe.

Conventions communes
--------------------
1. Erreurs : aucune fonction ne lève d'exception vers l'agent. Elle renvoie
   {"ok": False, "code": "...", "message": "..."} (voir `Erreur`, `erreur()`).
   Le message est rédigé pour que le modèle puisse en tirer une action.
2. Dates : ISO 8601 avec le fuseau Africa/Dakar, partout
   (ex. "2026-11-19T16:30:00+00:00" — Dakar est en UTC+0 toute l'année).
3. Écritures : creer_visite, deplacer_visite, annuler_visite et envoyer_brouillon
   ne sont JAMAIS appelées sans validation humaine. C'est le graphe de l'agent qui
   l'impose, pas le modèle.
4. État : chaque brique expose verifier_etat(), sans argument ni effet de bord,
   qui renvoie {"ok": True, "latence_ms": int} ou une `Erreur`.

Ce fichier ne dépend que de la bibliothèque standard : chacun peut l'importer
et coder contre ces signatures avec de fausses données.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Protocol, TypedDict, Union

# --------------------------------------------------------------------------- #
# Règles de l'agence                                                          #
# --------------------------------------------------------------------------- #

FUSEAU = "Africa/Dakar"
DUREE_VISITE_MIN = 45
HEURE_OUVERTURE = 9          # première visite à 9 h 00
HEURE_FERMETURE = 18         # dernière visite terminée au plus tard à 18 h 00
JOURS_OUVRES = (0, 1, 2, 3, 4, 5)   # lundi (0) à samedi (5), datetime.weekday()

# Conseillers (fictifs). L'identifiant d'agenda Google de chacun vient du .env :
# CALENDAR_ID_<CLE EN MAJUSCULES>, ex. CALENDAR_ID_AMINATA.
CONSEILLERS: dict[str, str] = {
    "aminata": "Aminata Diop",
    "moussa": "Moussa Ndiaye",
    "khady": "Khady Sarr",
}
Conseiller = Literal["aminata", "moussa", "khady"]

# --------------------------------------------------------------------------- #
# Format commun des réponses                                                  #
# --------------------------------------------------------------------------- #

CodeErreur = Literal[
    "ARGUMENT_INVALIDE",     # argument manquant ou mal formé
    "INTROUVABLE",           # bien, événement, brouillon ou message inexistant
    "CRENEAU_INDISPONIBLE",  # créneau pris entre-temps ou hors règles de l'agence
    "AUTORISATION",          # jeton OAuth invalide ou expiré : ne pas réessayer
    "INDISPONIBLE",          # brique injoignable : panne passagère possible
    "DELAI_DEPASSE",         # timeout
    "INTERNE",               # tout le reste
]


class Erreur(TypedDict):
    ok: Literal[False]
    code: CodeErreur
    message: str


class Etat(TypedDict):
    ok: Literal[True]
    latence_ms: int


class Confirmation(TypedDict):
    ok: Literal[True]


def erreur(code: CodeErreur, message: str) -> Erreur:
    return {"ok": False, "code": code, "message": message}
