"""Boîte à outils de l'agent : définitions envoyées au modèle + exécution.

L'agent ne connaît que l'interface BoiteAOutils. Aujourd'hui elle enveloppe un
contracts.Catalogue local ; à l'exercice 2 elle sera remplacée par le client MCP
sans toucher au graphe.
"""

from __future__ import annotations

from typing import Any, Protocol

from contracts import Catalogue, erreur


class BoiteAOutils(Protocol):
    def definitions(self) -> list[dict]: ...
    def appeler(self, nom: str, arguments: dict[str, Any]) -> dict: ...


DEFINITIONS_CATALOGUE: list[dict] = [
    {
        "name": "rechercher_biens",
        "description": (
            "Cherche dans le catalogue de l'agence les biens à louer DISPONIBLES qui "
            "correspondent aux critères. Tous les critères sont optionnels ; n'en passe "
            "que ceux exprimés par le client. Renvoie {ok, biens: [...]} trié par loyer "
            "croissant ; une liste vide signifie qu'aucun bien ne correspond."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["appartement", "studio", "villa", "chambre", "bureau"],
                    "description": "Type de bien. Un « F2/F3/F4 » est un appartement.",
                },
                "quartier": {
                    "type": "string",
                    "description": "Quartier de Dakar, ex. « Mermoz », « Point E », « Almadies ».",
                },
                "loyer_max": {
                    "type": "integer",
                    "description": "Loyer mensuel maximal en F CFA, ex. 400000.",
                },
                "pieces": {
                    "type": "integer",
                    "description": "Nombre de pièces exact : F3 = 3, F4 = 4.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "detail_bien",
        "description": (
            "Renvoie la fiche complète d'un bien (adresse, description, disponibilité) "
            "à partir de sa référence, ex. « SK-001 ». N'utilise que des références "
            "obtenues par rechercher_biens."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bien_id": {"type": "string", "description": "Référence du bien, ex. SK-001."},
            },
            "required": ["bien_id"],
            "additionalProperties": False,
        },
    },
]


class OutilsCatalogueLocal:
    """Expose un contracts.Catalogue local comme boîte à outils."""

    def __init__(self, catalogue: Catalogue):
        self._catalogue = catalogue
        self._fonctions = {
            "rechercher_biens": catalogue.rechercher_biens,
            "detail_bien": catalogue.detail_bien,
        }

    def definitions(self) -> list[dict]:
        return DEFINITIONS_CATALOGUE

    def appeler(self, nom: str, arguments: dict[str, Any]) -> dict:
        fonction = self._fonctions.get(nom)
        if fonction is None:
            return erreur("ARGUMENT_INVALIDE", f"Outil inconnu : {nom}.")
        try:
            return fonction(**arguments)
        except TypeError as e:
            return erreur("ARGUMENT_INVALIDE", f"Arguments invalides pour {nom} : {e}")
        except Exception as e:  # une brique ne doit jamais faire tomber la boucle
            return erreur("INTERNE", f"{nom} a échoué : {type(e).__name__}: {e}")
