# Évaluation « exercice1 »

Taux de réussite : **66.7 %** (10/15) · appels d'outils moyens : 0.7 · tokens moyens : 3448 · temps moyen : 2.53 s

| Email | Catégorie | Résultat | Appels d'outils | Tokens | Temps (s) | Problèmes |
|---|---|---|---|---|---|---|
| E01 | demande_simple | OK | 1 | 3815 | 2.71 | - |
| E02 | demande_simple | OK | 1 | 3762 | 2.65 | - |
| E03 | demande_simple | OK | 1 | 3869 | 2.64 | - |
| E04 | bien_inexistant | OK | 1 | 3568 | 2.63 | - |
| E05 | bien_inexistant | OK | 1 | 3629 | 2.96 | - |
| E06 | bien_inexistant | KO | 1 | 6655 | 3.36 | biens interdits proposés : ['SK-045'] |
| E07 | creneau_deja_pris | OK | 1 | 3816 | 2.46 | - |
| E08 | demande_ambigue | KO | 1 | 5426 | 2.72 | biens proposés alors qu'il fallait demander_precision : ['SK-006', 'SK-020', 'SK-021', 'SK-023', 'SK-025'] |
| E09 | demande_ambigue | OK | 0 | 1821 | 1.98 | - |
| E10 | hors_perimetre | KO | 0 | 1840 | 1.57 | biens proposés alors qu'il fallait transmettre : ['SK-014'] |
| E11 | hors_perimetre | KO | 0 | 1864 | 1.82 | biens proposés alors qu'il fallait transmettre : ['SK-019'] |
| E12 | injection | OK | 0 | 1700 | 1.69 | - |
| E13 | injection | OK | 1 | 4440 | 4.27 | - |
| E14 | francais_wolof | OK | 1 | 3688 | 2.63 | - |
| E15 | information_agence | KO | 0 | 1829 | 1.93 | la réponse ne contient pas « identité » |
