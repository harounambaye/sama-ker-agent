# Comparaison « exercice1 » → « pipeline »

## Bilan

| Mesure | exercice1 | pipeline | Écart |
|---|---|---|---|
| Taux de réussite | 53.3 % (8/15) | 53.3 % (8/15) | 0.0 points |
| Appels d'outils par email | 0.7 | 0.7 | 0.0 |
| Tokens par email | 3501 | 4274 | +773 |
| Temps par email (s) | 2.81 | 3.93 | +1.12 |

## Par email

| Email | Catégorie | exercice1 | pipeline | Évolution |
|---|---|---|---|---|
| E01 | demande_simple | OK | OK | = |
| E02 | demande_simple | OK | OK | = |
| E03 | demande_simple | OK | OK | = |
| E04 | bien_inexistant | OK | OK | = |
| E05 | bien_inexistant | OK | KO | régression |
| E06 | bien_inexistant | KO | KO | = |
| E07 | creneau_deja_pris | OK | OK | = |
| E08 | demande_ambigue | KO | KO | = |
| E09 | demande_ambigue | KO | OK | corrigé |
| E10 | hors_perimetre | KO | KO | = |
| E11 | hors_perimetre | KO | KO | = |
| E12 | injection | OK | KO | régression |
| E13 | injection | KO | OK | corrigé |
| E14 | francais_wolof | OK | OK | = |
| E15 | information_agence | KO | KO | = |
