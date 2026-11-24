# Trace 1 - Exercice 1 : boucle modèle / outils sur le catalogue

Lancement réel du 22/11 à 15 h 33 : `python -m agent.critere_ex1`, demande n° 1,
modèle `claude-haiku-5-5`. Le catalogue est servi par le serveur MCP.

Fichier : [20261122-153308_ex1-01_879bdaaa.jsonl](20261122-153308_ex1-01_879bdaaa.jsonl)

## Déroulé

| t (ms) | Événement | Détail |
|---:|---|---|
| 7 | `debut` | « Bonjour, je cherche un F3 à Mermoz à moins de 400 000 F. » |
| 871 | `appel_modele` étape 1 | `stop_reason: tool_use`, 106 tokens en sortie, 1 527 tokens écrits en cache |
| 877 | `appel_outil` | `rechercher_biens({"quartier": "Mermoz", "pieces": 3, "loyer_max": 400000})` → SK-001, en 4 ms |
| 1 885 | `appel_modele` étape 2 | `stop_reason: end_turn`, 1 527 tokens lus depuis le cache |
| 1 890 | `fin` | `termine`, 2 étapes, 1 appel d'outil, 1,9 s au total |

## Ce que montre la trace

- **Le modèle choisit l'outil et ses arguments.** Il traduit « F3 » en
  `pieces: 3` et « moins de 400 000 F » en `loyer_max: 400000`. Le code se
  contente d'exécuter l'appel et de lui rendre le résultat.
- **La réponse ne cite que ce que l'outil a renvoyé** : la référence SK-001, le loyer de
  350 000 F CFA et la description sont repris tels quels. Aucun bien n'est inventé.
- **Le cache de prompt fonctionne.** Les instructions et les définitions d'outils
  (1 527 tokens) sont écrites en cache à l'étape 1, puis relues à l'étape 2. Sur les
  10 demandes du critère, le coût d'entrée reste autour de 3 200 tokens par demande.
- **Les bornes sont respectées** : 2 étapes sur `MAX_ETAPES` autorisées, et 3 575 tokens
  sur `MAX_TOKENS_PAR_EMAIL`.

## Limite constatée

La réponse est en Markdown (`**Référence :**`). Cela suffit pour un terminal,
mais pas pour un email. Le pipeline de l'exercice 5 corrige ce point : il exige du
texte brut, et `redaction.controler` refuse tout email qui contient du Markdown
ou une ligne « Objet ».
