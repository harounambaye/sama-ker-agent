"""Crée la base SQLite du catalogue Sama Kër Immobilier : 30 biens fictifs.

Lancement, depuis la racine du dépôt :
    python -m mcp_server.creer_catalogue

Le script peut être relancé autant de fois que nécessaire :
il efface l'ancienne base et la recrée à l'identique.
Le format d'un bien suit contracts.Bien.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RACINE = Path(__file__).resolve().parent.parent


def chemin_base() -> Path:
    """Chemin de la base : variable CATALOGUE_DB du .env, relatif à la racine du dépôt."""
    chemin = Path(os.getenv("CATALOGUE_DB", "data/catalogue.sqlite"))
    return chemin if chemin.is_absolute() else RACINE / chemin


SCHEMA = """
CREATE TABLE biens (
    id          TEXT    PRIMARY KEY CHECK (id GLOB 'SK-[0-9][0-9][0-9]'),
    type        TEXT    NOT NULL CHECK (type IN ('appartement', 'studio', 'villa', 'chambre', 'bureau')),
    quartier    TEXT    NOT NULL,
    loyer_fcfa  INTEGER NOT NULL CHECK (loyer_fcfa > 0),
    pieces      INTEGER NOT NULL CHECK (pieces >= 1),
    adresse     TEXT    NOT NULL,
    disponible  INTEGER NOT NULL CHECK (disponible IN (0, 1)),
    description TEXT    NOT NULL
);
"""

# (id, type, quartier, loyer en F CFA par mois, pièces, adresse, disponible, description)
# Données fictives.
# SK-001 à SK-010 reprennent le catalogue factice de l'agent (agent/catalogue_factice.py),
# pour que les 10 demandes de agent/critere_ex1.py gardent les mêmes résultats attendus.
# SK-011 à SK-030 complètent le catalogue sans changer ces résultats.
# Cas prévus pour les tests : biens indisponibles (SK-003, SK-015, SK-022, SK-029),
# quartier avec accent et ligature (Sacré-Cœur), quartiers sans aucun bien (Médina, HLM).
BIENS = [
    ("SK-001", "appartement", "Mermoz",                350_000, 3, "Rue MZ-12, Mermoz, Dakar",                1, "F3 lumineux, 2 chambres, balcon."),
    ("SK-002", "appartement", "Mermoz",                450_000, 3, "Rue MZ-40, Mermoz, Dakar",                1, "F3 meublé, résidence avec gardien."),
    ("SK-003", "appartement", "Mermoz",                300_000, 3, "Rue MZ-7, Mermoz, Dakar",                 0, "F3 au rez-de-chaussée."),
    ("SK-004", "villa",       "Almadies",            1_500_000, 6, "Route des Almadies, Dakar",               1, "Villa avec piscine."),
    ("SK-005", "studio",      "Plateau",               150_000, 1, "Avenue Pompidou, Plateau, Dakar",         1, "Studio meublé proche des bureaux."),
    ("SK-006", "appartement", "Ouakam",                250_000, 2, "Cité Avion, Ouakam, Dakar",               1, "F2 vue mer partielle."),
    ("SK-007", "appartement", "Sacré-Cœur",            500_000, 4, "Sacré-Cœur 3, Dakar",                     1, "F4 familial, parking."),
    ("SK-008", "appartement", "Point E",               380_000, 3, "Rue de Kaolack, Point E, Dakar",          1, "F3 rénové."),
    ("SK-009", "chambre",     "Yoff",                   60_000, 1, "Yoff Village, Dakar",                     1, "Chambre en colocation."),
    ("SK-010", "appartement", "Ngor",                  300_000, 2, "Ngor Virage, Dakar",                      1, "F2 proche de la plage."),
    ("SK-011", "appartement", "Mermoz",                550_000, 4, "Rue MZ-55, Mermoz, Dakar",                1, "F4 avec terrasse, 3 chambres."),
    ("SK-012", "appartement", "Almadies",              850_000, 4, "Résidence Océane, Almadies, Dakar",       1, "F4 standing, vue mer, piscine commune."),
    ("SK-013", "villa",       "Almadies",            1_800_000, 7, "Zone 12, Almadies, Dakar",                1, "Villa 7 pièces, jardin et piscine."),
    ("SK-014", "appartement", "Sacré-Cœur",            360_000, 3, "Sacré-Cœur 2, Dakar",                     1, "F3 calme, cuisine équipée."),
    ("SK-015", "appartement", "Sacré-Cœur",            230_000, 2, "Sacré-Cœur 1, Dakar",                     0, "F2 au premier étage."),
    ("SK-016", "studio",      "Point E",               160_000, 1, "Rue 6, Point E, Dakar",                   1, "Studio meublé et climatisé."),
    ("SK-017", "bureau",      "Point E",               600_000, 4, "Rue de Fatick, Point E, Dakar",           1, "Plateau de bureaux de 120 m², 4 pièces."),
    ("SK-018", "bureau",      "Plateau",               900_000, 5, "Rue Carnot, Plateau, Dakar",              1, "Bureaux en centre-ville, ascenseur."),
    ("SK-019", "appartement", "Plateau",               500_000, 3, "Avenue Lamine Guèye, Plateau, Dakar",     1, "F3 au 5e étage, vue sur le port."),
    ("SK-020", "appartement", "Liberté 6",             180_000, 2, "Liberté 6 Extension, Dakar",              1, "F2 récent, proche du rond-point."),
    ("SK-021", "appartement", "Liberté 6",             270_000, 3, "Liberté 6, Dakar",                        1, "F3 familial, 2 chambres."),
    ("SK-022", "villa",       "Liberté 6",             650_000, 5, "Liberté 6, villa 6890, Dakar",            0, "Villa 5 pièces avec cour."),
    ("SK-023", "appartement", "Grand Yoff",            200_000, 3, "Arafat, Grand Yoff, Dakar",               1, "F3 abordable, quartier animé."),
    ("SK-024", "chambre",     "Grand Yoff",             50_000, 1, "Cité Millionnaire, Grand Yoff, Dakar",    1, "Chambre avec salle d'eau privée."),
    ("SK-025", "appartement", "Parcelles Assainies",   180_000, 3, "Unité 15, Parcelles Assainies, Dakar",    1, "F3 en rez-de-chaussée."),
    ("SK-026", "appartement", "Parcelles Assainies",   300_000, 5, "Unité 22, Parcelles Assainies, Dakar",    1, "F5 pour grande famille."),
    ("SK-027", "villa",       "Fann",                1_200_000, 6, "Fann Résidence, Dakar",                   1, "Villa de standing, quartier diplomatique."),
    ("SK-028", "appartement", "Ouakam",                380_000, 3, "Cité Comico, Ouakam, Dakar",              1, "F3 neuf, proche de la Corniche."),
    ("SK-029", "studio",      "Ngor",                  200_000, 1, "Ngor Village, Dakar",                     0, "Studio face à la mer."),
    ("SK-030", "appartement", "Yoff",                  280_000, 3, "Yoff Tonghor, Dakar",                     1, "F3 proche de l'aéroport."),
]


def creer_catalogue(chemin: Path | None = None) -> int:
    """Efface l'ancienne base, recrée la table et insère les 30 biens.

    Renvoie le nombre de biens présents dans la base à la fin.
    """
    chemin = chemin or chemin_base()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if chemin.exists():
        chemin.unlink()

    connexion = sqlite3.connect(chemin)
    try:
        with connexion:
            connexion.execute(SCHEMA)
            connexion.executemany(
                "INSERT INTO biens (id, type, quartier, loyer_fcfa, pieces, adresse, disponible, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                BIENS,
            )
        nombre = connexion.execute("SELECT COUNT(*) FROM biens").fetchone()[0]
    finally:
        connexion.close()
    return nombre


if __name__ == "__main__":
    total = creer_catalogue()
    print(f"Base créée : {chemin_base()}")
    print(f"{total} biens enregistrés")
    if total != 30:
        raise SystemExit("Erreur : le catalogue doit contenir exactement 30 biens.")
