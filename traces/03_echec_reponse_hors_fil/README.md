# Trace 3 - Échec analysé : la réponse du client arrive hors du fil

Lancement réel du 22/11 à 16 h 08, avec le modèle `claude-haiku-5-5`.

Fichier : [20261122-160851_pipeline_2226d6c4.jsonl](20261122-160851_pipeline_2226d6c4.jsonl)

## Ce qui s'est passé

Après l'envoi des trois créneaux sur `fil-m0007` (trace 2), on simule la réponse
d'Awa : « Le deuxième créneau me convient ». La commande tapée était :

```
python -m agent.conseiller demande "Le deuxième créneau me convient" --de "Awa <awa@example.com>" --fil <fil affiché>
```

Sous Windows, `cmd` interprète `<` et `>` comme des redirections. L'option `--fil`
n'a donc pas reçu `fil-m0007`, et la messagerie factice a ouvert un **nouveau
fil, `fil-m0009`**, sans historique.

| t (ms) | Événement | Détail |
|---:|---|---|
| 1 571 | `appel_modele` (tri) | 75 tokens en entrée, et 2 238 lus depuis le cache |
| 1 572 | `tri` | `categorie: hors_perimetre`, avec le motif « Le client mentionne un deuxième créneau mais aucun bloc creneaux_proposes n'est fourni, impossible de confirmer un choix. » |
| 1 573 | `parcours` | `transmettre` |
| 1 577 | `transmis_conseiller` | libellé « transmis à un conseiller », aucun brouillon |

## Analyse

- **Le symptôme** : la demande n'est pas traitée automatiquement. Un client qui
  choisit un créneau devrait obtenir une visite.
- **La cause** : la conversation est indexée par l'identifiant du fil Gmail. Sur un
  fil neuf, rien n'a jamais été proposé : le code n'a donc aucun créneau à
  transmettre au tri, et « le deuxième » ne renvoie à rien.
- **Le comportement de l'agent était le bon.** Le modèle n'a pas deviné un
  créneau, et le code n'a rien écrit. La demande est passée à un humain, avec
  un motif qui explique exactement pourquoi. Inventer « samedi 10 h » aurait
  créé une visite fausse dans l'agenda d'un conseiller.
- **Le vrai défaut était ailleurs** : dans l'outil du poste, qui affichait un
  gabarit `<fil affiché>` à remplacer à la main.

## Correction

- **Commit 363beb8** : après l'envoi de créneaux, `conseiller` affiche la commande
  exacte, déjà remplie, pour simuler la réponse du client (`--fil fil-m0007`).
  Le relancement suivant (trace 2, deb5243e) arrive sur le bon fil et donne
  `confirmation` avec `numero_creneau: 2`.
- **Avec le vrai Gmail**, la question ne se pose pas : la réponse du client
  porte le `threadId` d'origine, et `MessagerieGoogle` le transmet tel quel.

## Ce qui reste vrai

Si un client écrit dans un nouvel email « je prends le deuxième créneau »,
l'agent transmettra à un conseiller. C'est voulu : sans les créneaux proposés
sous les yeux, aucune décision sûre n'est possible. Ce cas n'est pas dans les
15 emails de l'évaluation, ce serait un bon 16e cas.
