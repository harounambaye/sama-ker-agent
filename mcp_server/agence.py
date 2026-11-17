"""Informations sur l'agence Sama Kër Immobilier, exposées comme ressource MCP.

Les horaires et la durée des visites viennent de contracts.py : ce sont les mêmes
règles que celles appliquées par le code Google Calendar.
Les conditions de location sont fictives.
"""

from __future__ import annotations

from contracts import DUREE_VISITE_MIN, FUSEAU, HEURE_FERMETURE, HEURE_OUVERTURE

ZONES_COUVERTES = [
    "Almadies", "Fann", "Grand Yoff", "Liberté 6", "Mermoz", "Ngor", "Ouakam",
    "Parcelles Assainies", "Plateau", "Point E", "Sacré-Cœur", "Yoff",
]


def informations_agence() -> str:
    """Renvoie la fiche de l'agence au format Markdown."""
    zones = ", ".join(ZONES_COUVERTES)
    return f"""# Agence Sama Kër Immobilier (Dakar)

## Horaires de visite
- Du lundi au samedi, de {HEURE_OUVERTURE} h à {HEURE_FERMETURE} h (fuseau {FUSEAU}).
- Pas de visite le dimanche.
- Chaque visite dure {DUREE_VISITE_MIN} minutes et se fait avec un conseiller.

## Zones couvertes
{zones}.
L'agence ne propose aucun bien en dehors de ces quartiers.

## Conditions de location
- Bail d'un an, renouvelable.
- À la signature : un mois de loyer d'avance, deux mois de caution et un mois de frais d'agence.
- Pièces à fournir : pièce d'identité et justificatif de revenus.
- Les loyers affichés ne se négocient pas avec l'agent : toute demande de négociation,
  réclamation ou litige est transmise à un conseiller.
"""