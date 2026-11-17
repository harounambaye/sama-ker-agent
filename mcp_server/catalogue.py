"""Outils du catalogue Sama Kër Immobilier, lus dans la base SQLite.

Conforme à contracts.Catalogue : aucune exception ne remonte vers l'agent,
chaque erreur est renvoyée au format {"ok": False, "code": ..., "message": ...}.
La base est créée par : python -m mcp_server.creer_catalogue
"""

from __future__ import annotations

import sqlite3
import time
import unicodedata
from pathlib import Path

from contracts import Bien, erreur
from mcp_server.creer_catalogue import chemin_base

TYPES_VALIDES = ("appartement", "studio", "villa", "chambre", "bureau")
NOMBRE_BIENS_ATTENDU = 30

_LIGATURES = str.maketrans({"œ": "oe", "Œ": "Oe", "æ": "ae", "Æ": "Ae"})


def normaliser(texte: str) -> str:
    """« Sacré-Cœur », « sacre coeur » et « SACRE-COEUR » donnent la même clé : « sacre coeur »."""
    texte = texte.translate(_LIGATURES)
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().replace("-", " ").split())


def _ligne_vers_bien(ligne: sqlite3.Row) -> Bien:
    """Transforme une ligne de la table en dictionnaire au format contracts.Bien."""
    return {
        "id": ligne["id"],
        "type": ligne["type"],
        "quartier": ligne["quartier"],
        "loyer_fcfa": ligne["loyer_fcfa"],
        "pieces": ligne["pieces"],
        "adresse": ligne["adresse"],
        "disponible": bool(ligne["disponible"]),
        "description": ligne["description"],
    }


class CatalogueSQLite:
    """Accès en lecture seule au catalogue."""

    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or chemin_base()

    def _connecter(self) -> sqlite3.Connection:
        """Ouvre la base en lecture seule. Lève sqlite3.Error si elle n'existe pas."""
        connexion = sqlite3.connect(f"file:{self.chemin.as_posix()}?mode=ro", uri=True)
        connexion.row_factory = sqlite3.Row
        connexion.create_function("normaliser", 1, normaliser, deterministic=True)
        return connexion

    def rechercher_biens(
        self,
        type: str | None = None,
        quartier: str | None = None,
        loyer_max: int | None = None,
        pieces: int | None = None,
    ) -> dict:
        """Renvoie les biens DISPONIBLES qui respectent tous les critères donnés,
        triés par loyer croissant. Liste vide si aucun bien ne correspond."""
        if type is not None and type not in TYPES_VALIDES:
            return erreur("ARGUMENT_INVALIDE",
                          f"Type « {type} » inconnu. Valeurs possibles : {', '.join(TYPES_VALIDES)}. "
                          "Un F2, F3 ou F4 est un « appartement » ; préciser le nombre de pièces avec pieces.")
        if loyer_max is not None and (not isinstance(loyer_max, int) or loyer_max <= 0):
            return erreur("ARGUMENT_INVALIDE",
                          "loyer_max doit être un entier positif en F CFA, par exemple 400000.")
        if pieces is not None and (not isinstance(pieces, int) or pieces <= 0):
            return erreur("ARGUMENT_INVALIDE",
                          "pieces doit être un entier positif : F3 = 3, F4 = 4.")

        conditions = ["disponible = 1"]
        valeurs: list = []
        if type is not None:
            conditions.append("type = ?")
            valeurs.append(type)
        if quartier and quartier.strip():
            conditions.append("normaliser(quartier) = ?")
            valeurs.append(normaliser(quartier))
        if loyer_max is not None:
            conditions.append("loyer_fcfa <= ?")
            valeurs.append(loyer_max)
        if pieces is not None:
            conditions.append("pieces = ?")
            valeurs.append(pieces)

        requete = f"SELECT * FROM biens WHERE {' AND '.join(conditions)} ORDER BY loyer_fcfa, id"
        try:
            connexion = self._connecter()
            try:
                lignes = connexion.execute(requete, valeurs).fetchall()
            finally:
                connexion.close()
        except sqlite3.Error as exc:
            return erreur("INDISPONIBLE",
                          f"Catalogue inaccessible ({exc}). Ne propose aucun bien de mémoire : "
                          "signale le problème à un conseiller.")
        return {"ok": True, "biens": [_ligne_vers_bien(l) for l in lignes]}

    def detail_bien(self, bien_id: str) -> dict:
        """Renvoie la fiche complète d'un bien à partir de sa référence, par exemple « SK-001 »."""
        reference = (bien_id or "").strip().upper()
        if not reference:
            return erreur("ARGUMENT_INVALIDE",
                          "bien_id est obligatoire, par exemple « SK-001 ».")
        try:
            connexion = self._connecter()
            try:
                ligne = connexion.execute("SELECT * FROM biens WHERE id = ?", (reference,)).fetchone()
            finally:
                connexion.close()
        except sqlite3.Error as exc:
            return erreur("INDISPONIBLE",
                          f"Catalogue inaccessible ({exc}). Signale le problème à un conseiller.")
        if ligne is None:
            return erreur("INTROUVABLE",
                          f"Aucun bien de référence {reference}. "
                          "Utilise une référence renvoyée par rechercher_biens.")
        return {"ok": True, "bien": _ligne_vers_bien(ligne)}

    def verifier_etat(self) -> dict:
        """Vérifie que la base s'ouvre et contient les 30 biens. Ne modifie rien."""
        debut = time.perf_counter()
        try:
            connexion = self._connecter()
            try:
                nombre = connexion.execute("SELECT COUNT(*) FROM biens").fetchone()[0]
            finally:
                connexion.close()
        except sqlite3.Error as exc:
            return erreur("INDISPONIBLE",
                          f"Catalogue inaccessible ({exc}). "
                          "Lancer : python -m mcp_server.creer_catalogue")
        if nombre != NOMBRE_BIENS_ATTENDU:
            return erreur("INTERNE",
                          f"Le catalogue contient {nombre} biens au lieu de {NOMBRE_BIENS_ATTENDU}. "
                          "Lancer : python -m mcp_server.creer_catalogue")
        return {"ok": True, "latence_ms": round((time.perf_counter() - debut) * 1000)}