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
python -m mcp_server.creer_catalogue    # base du catalogue (30 biens)
```

L'agent lance lui-même le serveur MCP du catalogue (`MCP_TRANSPORT=stdio`), ou se
connecte à un serveur déjà lancé (`MCP_TRANSPORT=http`, `MCP_URL`). Pour travailler
sans serveur : `CATALOGUE=factice` (mêmes biens SK-001 à SK-010, en mémoire).

## Lancer l'agent (exercice 1)

```bash
python -m agent "Je cherche un F3 à Mermoz à moins de 400 000 F" -v   # une demande, étapes affichées
python -m agent.critere_ex1                                           # critère d'acceptation : 10 demandes
```

Chaque traitement écrit sa trace dans `traces/brutes/<date>_<id>.jsonl` : un
événement par appel au modèle (tokens, cache, raison d'arrêt, durée) et par
appel d'outil (arguments, résultat, durée).

**Catalogue** ([agent/outils_mcp.py](agent/outils_mcp.py)) : les outils proposés au modèle
sont ceux que le serveur MCP expose (`rechercher_biens`, `detail_bien`) ; `verifier_etat`
reste réservé au code du graphe. Une session MCP est ouverte une fois et sert tous les appels.

**Boucle** ([agent/graphe.py](agent/graphe.py)) : graphe LangGraph `modele → outils → modele`,
modèle appelé avec le SDK `anthropic`. Bornes : `MAX_ETAPES` appels au modèle et
`MAX_TOKENS_PAR_EMAIL` tokens par demande ; au-delà, l'agent s'arrête et passe la
main à un conseiller. Une erreur d'outil n'interrompt pas la boucle : elle revient
au modèle au format `{"ok": false, "code", "message"}`. Une erreur de l'API du
modèle termine le traitement sans réponse inventée.

## État des briques

```bash
python -m agent.etat      # code de sortie 0 si tout est ok, 1 sinon
```

```
État des briques (modèle : claude-haiku-5-5)
  ok      modele     312 ms
  ok      catalogue  2 ms
  ok      calendar   0 ms · factice (Calendar pas encore branché)
  ok      gmail      0 ms · factice (Gmail pas encore branché)
```

Chaque brique expose `verifier_etat()` sans argument ni effet de bord. Le code
du graphe, pas le modèle, l'appelle : au démarrage (une brique en erreur bloque
le lancement), avant chaque email (résultat gardé une minute), après une erreur
d'outil et juste avant une écriture validée (vérification forcée). La sonde du
modèle passe par l'API des modèles et ne consomme aucun token.

## Validation humaine

Aucun email ne part et aucune visite n'est créée, déplacée ou annulée sans
l'accord d'un conseiller. Le modèle n'a **aucun outil d'écriture** : le graphe
([agent/conversation.py](agent/conversation.py)) s'arrête sur `interrupt()` avant
toute écriture, et seul le nœud `ecrire` écrit, après la décision du conseiller.

```
[boucle modele/outils] -> preparer (brouillon dans le fil, libellé « en attente »)
  -> valider  ⏸ pause, état sauvegardé par fil Gmail (checkpointer SQLite)
       approuver / modifier -> ecrire : brique revérifiée, puis envoi, libellé « répondu »
       refuser              -> libellé « transmis à un conseiller », rien n'est écrit
       brique en panne      -> rien n'est écrit, validation redemandée avec l'incident
```

```bash
# terminal 1 : un email arrive (messagerie factice) et est traité jusqu'à la pause
python -m agent.conseiller demande "Je cherche un F3 à Mermoz à moins de 400 000 F" --de "Awa <awa@example.com>"

# terminal 2, plus tard : le conseiller décide
python -m agent.conseiller attente
python -m agent.conseiller valider --conseiller Khady     # o / m / n / p
```

Tant que la PR Google n'est pas fusionnée, Gmail et Calendar sont des factices
conformes aux contrats, enregistrés dans `data/factices/` (`FACTICES_DIR`).

## Tests

```bash
python -m pytest          # hors ligne : ni réseau, ni clé, ni .env
```

Les sections *configuration des accès Google*, *serveur MCP* et *évaluation*
seront complétées par chaque pull request.
