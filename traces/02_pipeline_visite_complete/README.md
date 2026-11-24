# Trace 2 - Pipeline complet : de la demande à la visite confirmée (fil-m0007)

Lancement réel du 22/11, entre 16 h 06 et 16 h 20, avec `python -m agent.conseiller`.
Le modèle est `claude-haiku-5-5`. Gmail et Calendar sont factices, le catalogue
passe par MCP.

La conversation suit un seul fil Gmail, `fil-m0007`. Il y a un fichier par commande
lancée, et le graphe reprend chaque fois là où il s'était arrêté, grâce au
checkpointer SQLite indexé par l'identifiant du fil.

| # | Fichier | Commande | Ce qui se passe |
|---|---|---|---|
| 1 | [..._91942b2d.jsonl](20261122-160650_pipeline_91942b2d.jsonl) | `demande "Un F3 à Mermoz…, samedi matin"` | tri, recherche, rédaction, puis ⏸ validation |
| 2 | [..._1671cff8.jsonl](20261122-160726_pipeline_1671cff8.jsonl) | `valider --conseiller Khady` | approuvé, la proposition est envoyée |
| 3 | [..._deb5243e.jsonl](20261122-161334_pipeline_deb5243e.jsonl) | `demande "Le deuxième créneau…" --fil fil-m0007` | tri « confirmation », puis ⏸ validation de la visite |
| 4 | [..._c074b0c0.jsonl](20261122-161352_pipeline_c074b0c0.jsonl) | `valider` | visite créée, email de confirmation rédigé, puis ⏸ |
| 5 | [..._5d3289dd.jsonl](20261122-162020_pipeline_5d3289dd.jsonl) | `valider` | la confirmation est envoyée |

## 1. La demande (91942b2d)

1. **Tri** : un appel au modèle, dont la sortie est un JSON conforme au schéma.
   - Champs extraits : `categorie: demande_visite`, besoin `{appartement, Mermoz, 3 pièces, loyer_max 400 000}`, disponibilités `{jour: samedi, plage: matin}`.
   - Le code en déduit le parcours `proposer`.
2. **Recherche**, menée en parallèle :
   - Agenda : la fenêtre est calculée par le code (`dates.fenetre`) et donne « samedi 28 novembre, matin ». Sur 30 créneaux libres, `recherche.choisir` en retient 3 : 9 h 00, 10 h 00 et 11 h 15.
   - Catalogue : un seul bien correspond, SK-001 (350 000 F, Rue MZ-12).
3. **Rédaction** : un second appel au modèle.
   - Le modèle reçoit le bien et le **nombre** de créneaux, mais jamais leurs dates. Il écrit le repère `[CRENEAUX]`, que le code remplace par la liste exacte.
   - `controler` vérifie ensuite que la seule référence citée, SK-001, figure bien dans les faits.
4. **Validation** : le brouillon d0008 est créé dans le fil. Le graphe s'arrête sur
   `interrupt()` et attend le conseiller.

Coût : 2 appels au modèle (459 tokens en entrée et 489 en sortie hors cache), en 5,7 s.

## 2 à 5. La suite de la conversation

- **Envoi (1671cff8)** : Khady approuve. Le nœud `ecrire` revérifie la messagerie, puis
  envoie d0008. La même commande traite aussi un deuxième fil en attente (fil-m0005).
- **Choix du client (deb5243e)** : la réponse arrive dans le même fil. Le code
  retrouve les 3 créneaux proposés et les donne, numérotés, au tri.
  - Le modèle répond `categorie: confirmation` et `numero_creneau: 2`.
  - Le code fait correspondre ce numéro au créneau « 10 h 00 avec Aminata ».
  - **Aucun appel de rédaction n'a lieu à ce stade** : la proposition `creer_visite` est construite entièrement par le code, avec le bien, l'adresse, le client et le créneau.
- **Visite (c074b0c0)** : Khady approuve, et `creer_visite` crée l'événement dans
  l'agenda d'Aminata (`deja_existante: false`). L'identifiant de l'événement est
  déterministe, si bien que relancer la commande ne crée pas de doublon. L'email de
  confirmation est ensuite rédigé, avec la date insérée par le code, puis soumis à
  validation à son tour.
- **Confirmation (5d3289dd)** : elle est envoyée. Le fil est terminé.

**Bilan** : 4 appels au modèle pour toute la conversation, aucune écriture sans
validation, et aucune date écrite par le modèle.

## Défauts relevés dans cette trace, puis corrigés

| Constat | Cause | Correction |
|---|---|---|
| L'email de la proposition (d0008) n'a pas de ligne vide entre les paragraphes. | La consigne de forme ne le demandait pas. | Le prompt de rédaction demande désormais « Sépare chaque paragraphe par une ligne vide ». La confirmation (c074b0c0) est correctement aérée. |
| La note du conseiller décrit la mécanique interne (« les créneaux seront insérés par le code », « le repère [CRENEAUX] devant être remplacé »). | Le modèle commente les règles qu'il a reçues. | Le prompt l'interdit, et le filet `redaction.nettoyer_note` supprime les phrases concernées (commit 6c21354, test `test_note_sans_phrase_sur_la_mecanique`). |

Le conseiller relit chaque email : ces défauts n'auraient jamais atteint le
client sans être vus. Ils ont tout de même été corrigés, parce qu'ils lui
font perdre du temps.
