"""Catalogue factice conforme à contracts.Catalogue.

TEMPORAIRE : permet de développer la boucle avant la PR de Fatou (base SQLite +
serveur MCP). Sera supprimé à l'exercice 2, quand l'agent passera par le client MCP.
"""

from __future__ import annotations

import time
import unicodedata

from contracts import Bien, Catalogue, erreur

_BIENS: list[Bien] = [
    {"id": "SK-001", "type": "appartement", "quartier": "Mermoz", "loyer_fcfa": 350_000,
     "pieces": 3, "adresse": "Rue MZ-12, Mermoz, Dakar", "disponible": True,
     "description": "F3 lumineux, 2 chambres, balcon."},
    {"id": "SK-002", "type": "appartement", "quartier": "Mermoz", "loyer_fcfa": 450_000,
     "pieces": 3, "adresse": "Rue MZ-40, Mermoz, Dakar", "disponible": True,
     "description": "F3 meublé, résidence avec gardien."},
    {"id": "SK-003", "type": "appartement", "quartier": "Mermoz", "loyer_fcfa": 300_000,
     "pieces": 3, "adresse": "Rue MZ-7, Mermoz, Dakar", "disponible": False,
     "description": "F3 au rez-de-chaussée."},
    {"id": "SK-004", "type": "villa", "quartier": "Almadies", "loyer_fcfa": 1_500_000,
     "pieces": 6, "adresse": "Route des Almadies, Dakar", "disponible": True,
     "description": "Villa avec piscine."},
    {"id": "SK-005", "type": "studio", "quartier": "Plateau", "loyer_fcfa": 150_000,
     "pieces": 1, "adresse": "Avenue Pompidou, Plateau, Dakar", "disponible": True,
     "description": "Studio meublé proche des bureaux."},
    {"id": "SK-006", "type": "appartement", "quartier": "Ouakam", "loyer_fcfa": 250_000,
     "pieces": 2, "adresse": "Cité Avion, Ouakam, Dakar", "disponible": True,
     "description": "F2 vue mer partielle."},
    {"id": "SK-007", "type": "appartement", "quartier": "Sacré-Cœur", "loyer_fcfa": 500_000,
     "pieces": 4, "adresse": "Sacré-Cœur 3, Dakar", "disponible": True,
     "description": "F4 familial, parking."},
    {"id": "SK-008", "type": "appartement", "quartier": "Point E", "loyer_fcfa": 380_000,
     "pieces": 3, "adresse": "Rue de Kaolack, Point E, Dakar", "disponible": True,
     "description": "F3 rénové."},
    {"id": "SK-009", "type": "chambre", "quartier": "Yoff", "loyer_fcfa": 60_000,
     "pieces": 1, "adresse": "Yoff Village, Dakar", "disponible": True,
     "description": "Chambre en colocation."},
    {"id": "SK-010", "type": "appartement", "quartier": "Ngor", "loyer_fcfa": 300_000,
     "pieces": 2, "adresse": "Ngor Virage, Dakar", "disponible": True,
     "description": "F2 proche de la plage."},
]


def _norm(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().replace("-", " ").split())


class CatalogueFactice(Catalogue):
    def rechercher_biens(self, type=None, quartier=None, loyer_max=None, pieces=None):
        if loyer_max is not None and loyer_max <= 0:
            return erreur("ARGUMENT_INVALIDE", "loyer_max doit être un entier positif en F CFA.")
        if pieces is not None and pieces <= 0:
            return erreur("ARGUMENT_INVALIDE", "pieces doit être un entier positif (F3 = 3).")
        biens = [
            b for b in _BIENS
            if b["disponible"]
            and (type is None or b["type"] == type)
            and (quartier is None or _norm(b["quartier"]) == _norm(quartier))
            and (loyer_max is None or b["loyer_fcfa"] <= loyer_max)
            and (pieces is None or b["pieces"] == pieces)
        ]
        return {"ok": True, "biens": sorted(biens, key=lambda b: b["loyer_fcfa"])}

    def detail_bien(self, bien_id):
        for b in _BIENS:
            if b["id"] == bien_id.strip().upper():
                return {"ok": True, "bien": b}
        return erreur("INTROUVABLE", f"Aucun bien de référence {bien_id}. "
                      "Utilise une référence renvoyée par rechercher_biens.")

    def verifier_etat(self):
        t0 = time.perf_counter()
        return {"ok": True, "latence_ms": round((time.perf_counter() - t0) * 1000)}
