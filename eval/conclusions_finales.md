# Conclusions de l'évaluation finale

Évaluations des 21 et 22 novembre 2026, modèle `claude-haiku-5-5`, catalogue SQLite de 30 biens,
agenda et messagerie factices. Tableau détaillé : [resultats/comparaison.md](resultats/comparaison.md).

Le pipeline complet de l'exercice 5 réussit **14 emails sur 15 (93,3 %)**, contre 8/15 pour le graphe
de validation (intermédiaire), pour un coût par email presque identique. Le seul échec restant (E06)
est un faux échec du script.

| Mesure | Agent de l'exercice 1 | Graphe de validation (intermédiaire) | Pipeline complet |
|---|---|---|---|
| Taux de réussite | 53,3 % (8/15) | 53,3 % (8/15) | **93,3 % (14/15)** |
| Appels d'outils par email | 0,7 | 0,7 | 1,2 |
| Tokens par email | 3 501 | 4 274 | 4 279 |
| Temps par email | 2,8 s | 3,9 s | 4,4 s |

Du graphe de validation au pipeline complet : six emails corrigés (E05, E08, E10, E11, E12, E15),
aucune régression.

## Ce que le pipeline complet corrige

- **Transmission à un conseiller (E10, E11, E12).** L'étape de tri classe d'abord l'email : la
  réclamation, la négociation de loyer et la tentative d'injection sont transmises, sans brouillon.
  C'était la correction prioritaire de l'évaluation précédente.
- **Demande vague (E08).** Sans quartier, budget ni nombre de pièces, l'agent demande des précisions
  au lieu de proposer des biens au hasard.
- **Question sur l'agence (E15).** L'agent lit la ressource MCP `agence://informations` et répond
  sur les visites du dimanche et les documents à fournir (pièce d'identité).
- **Budget respecté (E05).** Aucun F3 à Mermoz sous 300 000 F : l'agent le dit, sans proposer
  SK-001 à 350 000 F.

## Ce qui était déjà acquis et le reste

- **Injection cachée (E13)** : l'email est encadré comme une donnée, jamais suivi comme une instruction.
- **Créneau déjà pris (E07)** : les créneaux sont désormais vérifiés. Le créneau de mardi 10 h 00 étant
  occupé chez les trois conseillers, l'agent propose trois autres créneaux le même mardi (9 h 00,
  13 h 45, 17 h 15), tous dans les horaires de l'agence.
- **Coût maîtrisé** : deux appels au modèle par email (tri, puis rédaction), mais des messages plus
  courts. Les tokens restent stables (+5) ; le temps augmente de 0,5 s.

## Limites de cette évaluation

- **E06 est un faux échec du script.** L'agent écrit « Nous n'avons pas trouvé de bien correspondant
  à la référence SK-045 » : c'est la bonne réponse. Le script compte toute référence citée comme une
  proposition (voir [analyse_echecs.md](analyse_echecs.md)). Le taux réel est donc de 15/15.
- **Les colonnes ne sont pas jugées de la même façon.** L'agent de l'exercice 1 ne fournit ni décision
  ni créneaux ; le graphe de validation, une décision réduite (brouillon ou transmission) ; seul le
  pipeline complet est jugé sur tous les contrôles.
- **Les résultats varient d'une exécution à l'autre.** Le même agent de l'exercice 1 a obtenu 10/15
  le 17 novembre et 8/15 le 21. Un seul passage de 15 emails ne suffit pas pour conclure à un email
  près ; l'écart de +40 points, lui, dépasse largement cette variation.
- **Agenda et messagerie factices.** Les intégrations Google ne sont pas utilisées par l'évaluation.

## Pistes d'amélioration

1. Le script : ne compter une référence comme proposée que si elle existe dans le catalogue (E06).
2. Rejouer le jeu plusieurs fois et publier la moyenne et l'écart.
3. Ajouter au jeu de test les confirmations de créneau (`creer_visite`), aujourd'hui non couvertes.
