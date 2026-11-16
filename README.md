# Sama Kër Immobilier - agent de demandes de visite

Agent qui lit les demandes de visite reçues sur Gmail, cherche les biens dans le
catalogue (serveur MCP), propose des créneaux libres de Google Calendar, prépare
la réponse et inscrit la visite - **chaque envoi et chaque écriture dans l'agenda
passent par la validation d'un conseiller.**

> Projet pédagogique - Programme Data & IA, Orange Digital Center.

## Arborescence

| Dossier | Propriétaire | Contenu |
|---|---|---|
| `agent/` | Harouna | boucle, graphe LangGraph, validation, pipeline |
| `mcp_server/` | Fatou | catalogue SQLite, outils, ressource agence |
| `integrations/google/` | Papa | `auth.py`, `calendar.py`, `gmail.py` |
| `eval/` | Fatou | 15 emails de test, résultats attendus, script |
| `traces/` | Harouna | trois traitements complets, dont un échec analysé |
| `contracts.py` | Harouna | types et signatures partagés |

## Démarrage rapide

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate    -    Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # puis remplir les valeurs
```

## Lancer l'agent (exercice 1)

```bash
python -m agent "Je cherche un F3 à Mermoz à moins de 400 000 F" -v   # une demande, étapes affichées
python -m agent.critere_ex1                                           # critère d'acceptation : 10 demandes
```

Chaque traitement écrit sa trace dans `traces/brutes/<date>_<id>.jsonl` : un
événement par appel au modèle (tokens, cache, raison d'arrêt, durée) et par
appel d'outil (arguments, résultat, durée).

**Boucle** ([agent/graphe.py](agent/graphe.py)) : graphe LangGraph `modele → outils → modele`,
modèle appelé avec le SDK `anthropic`. Bornes : `MAX_ETAPES` appels au modèle et
`MAX_TOKENS_PAR_EMAIL` tokens par demande ; au-delà, l'agent s'arrête et passe la
main à un conseiller. Une erreur d'outil n'interrompt pas la boucle : elle revient
au modèle au format `{"ok": false, "code", "message"}`. Une erreur de l'API du
modèle termine le traitement sans réponse inventée.

Les sections *configuration des accès Google*, *serveur MCP* et *évaluation*
seront complétées par chaque pull request.
