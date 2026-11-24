# Traces analysées

Chaque traitement écrit un fichier JSONL, avec une ligne par événement : chaque
appel au modèle (tokens, cache, raison d'arrêt, durée), chaque appel d'outil
(arguments, résultat, durée) et chaque décision. Les fichiers bruts vont dans
`traces/brutes/`, qui n'est pas versionné. Ce dossier ne garde que les traces
retenues et analysées, toutes issues de **lancements réels**, avec le modèle
`claude-haiku-5-5`, le 22/11.

| # | Traitement | Résultat |
|---|---|---|
| [1](01_exercice1_recherche/) | Exercice 1 : une demande, une boucle modèle → outil → modèle sur le catalogue MCP | réponse juste, 2 étapes, cache relu |
| [2](02_pipeline_visite_complete/) | Pipeline complet : demande → 3 créneaux → choix du client → visite dans l'agenda → confirmation | 5 validations humaines, 4 appels au modèle ; 2 défauts de forme relevés et corrigés |
| [3](03_echec_reponse_hors_fil/) | **Échec analysé** : la réponse du client arrive sur un nouveau fil | transmise à un conseiller, rien n'est inventé ; cause dans l'outil du poste, corrigée |

Lire une trace :

```bash
python -c "import json,sys; [print(json.loads(l)['type'], l[:160]) for l in open(sys.argv[1], encoding='utf-8')]" traces/02_pipeline_visite_complete/20261122-160650_pipeline_91942b2d.jsonl
```
