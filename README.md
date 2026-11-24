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
  ok      calendar   0 ms · factice
  ok      gmail      0 ms · factice
```

Avec `BRIQUES=google`, la même commande sonde le vrai Calendar et le vrai Gmail.

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

Gmail et Calendar : factices conformes aux contrats, enregistrés dans
`data/factices/` (`BRIQUES=factice`, par défaut), ou intégrations Google
(`BRIQUES=google`, compte de test).

## Pipeline complet (exercice 5)

Le modèle **comprend** (tri) et **rédige** ; le **code** cherche, choisit les
créneaux, contrôle et décide ([agent/pipeline.py](agent/pipeline.py)).

```
email -> trier : 1 appel au modèle, sortie typée (catégorie, besoin, disponibilités)
  hors périmètre / injection -> libellé « transmis », aucun brouillon
  demande incomplète         -> brouillon qui demande ce qui manque      -> valider -> envoi
  question sur l'agence      -> réponse tirée de agence://informations   -> valider -> envoi
  demande de visite          -> catalogue // agenda (en parallèle)
                                -> 3 créneaux libres, jamais dans le passé
                                -> rédaction, créneaux insérés par le code -> valider -> envoi
  le client choisit un créneau (même fil) -> valider la visite -> création dans l'agenda
                                -> email de confirmation -> valider -> envoi
       créneau pris entre-temps -> nouveaux créneaux -> valider -> envoi
```

| Étape | Fichier | Garantie |
|---|---|---|
| Tri et extraction | [agent/tri.py](agent/tri.py) | sortie JSON conforme au schéma ; le parcours est décidé par le code |
| Dates | [agent/dates.py](agent/dates.py) | « samedi matin », « mardi prochain » -> fenêtre réelle, fuseau de Dakar |
| Recherche | [agent/recherche.py](agent/recherche.py) | catalogue et agenda en parallèle ; une brique en erreur est revérifiée, puis transmise |
| Rédaction | [agent/redaction.py](agent/redaction.py) | le modèle n'écrit aucune date ; toute référence citée vient des faits |
| Modèle | [agent/modele.py](agent/modele.py) | bascule sur `MODEL_SECOURS` si le modèle principal est surchargé |

Le fil Gmail est la clé de la conversation : quand le client répond, les créneaux
proposés sont retrouvés et numérotés pour le tri. Un email qui arrive sur un fil
déjà en attente de validation est laissé « à traiter ».

```bash
python -m agent.conseiller releve                     # emails « à traiter » de la messagerie
python -m agent.conseiller demande "Un F3 à Mermoz, 400 000 F max, samedi matin" --de "Awa <awa@example.com>"
python -m agent.conseiller valider --conseiller Khady  # envoi de la proposition
python -m agent.conseiller demande "Le deuxième créneau me convient" --de "Awa <awa@example.com>" --fil fil-m0001
python -m agent.conseiller valider --conseiller Khady  # visite, puis confirmation
```

### Démonstration sur le vrai compte Google

1. Fournis par l'équipe : `secrets/credentials.json` (client OAuth « application de bureau »,
   API Gmail et Calendar activées, votre adresse parmi les utilisateurs test) et l'accès au
   compte de test de l'agence. Rien de `secrets/` n'est versionné.
2. Dans le compte de l'agence : trois agendas (Aminata, Moussa, Khady) et un filtre Gmail
   « À : adresse de l'agence » -> libellé `SamaKer/A traiter`.
3. Dans `.env` : `BRIQUES=google`, `AGENCE_EMAIL`, `CALENDAR_ID_AMINATA`, `CALENDAR_ID_MOUSSA`,
   `CALENDAR_ID_KHADY`.
4. Vérification (crée les libellés manquants, n'envoie rien) :

```bash
python -m agent.preparer_google     # la première fois : connexion avec le compte de l'agence
```

Ensuite : écrire à l'agence depuis une autre adresse, `releve`, `valider` ; la réponse
arrive dans le même fil, la visite dans l'agenda du conseiller.

Pour l'évaluation, `agent.pipeline.resultat_evaluation()` renvoie la décision
(`repondre`, `demander_precision`, `transmettre`, `creer_visite`), le brouillon,
les créneaux proposés, les appels d'outils et les tokens.

## Observabilité et poste du conseiller

### Poste du conseiller dans le navigateur

```bash
streamlit run poste_conseiller.py        # http://localhost:8501, cette machine seulement
```

| Onglet | Contenu |
|---|---|
| Demandes | Les fils, du plus récent au plus ancien (⏸ à valider, ✅ envoyé, ↪ transmis, ✖ refusé). Pour le fil choisi : le **graphe avec le chemin suivi** (vert = étape franchie, orange = pause, gris = transmis), les appels au modèle, les tokens (cache compris) et le temps de l'agent, ce que le modèle a compris (tri), ce que le code a trouvé (biens, créneaux), la chronologie complète de la trace, et la validation : **Approuver**, modifier le texte, **Refuser** |
| Nouvel email | Avec la messagerie factice : exemples prêts à l'emploi (demande de visite, question, demande vague, injection, réclamation). Après l'envoi de créneaux, le fil propose de simuler la réponse du client. |
| Écritures validées | Chaque envoi et chaque visite exécutés après validation, avec le conseiller qui a validé |
| Évaluation | La comparaison et les conclusions de [eval/](eval/README.md) |

La barre latérale montre l'**état des quatre briques**, avec un bouton pour les revérifier, et
le nom du conseiller qui valide. Le poste et `python -m agent.conseiller` partagent le même
graphe, la même mémoire (le checkpointer) et les mêmes traces : on peut passer de l'un à l'autre.

Ce que le poste affiche vient des traces ([agent/observation.py](agent/observation.py)) :
- chaque nœud du pipeline y laisse un événement `noeud` (nom, durée, fini ou pause) ;
- chaque événement porte le fil traité ;
- le dessin est généré à partir du graphe compilé lui-même, il ne peut donc pas diverger du code.

### LangSmith et LangGraph Studio (en option)

Dans `.env` : `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY` (compte gratuit sur
smith.langchain.com) et `LANGSMITH_PROJECT`.
- **Traces LangSmith :** chaque exécution du graphe (nœuds, état en entrée et en sortie) et
  chaque appel au modèle (messages, réponse, tokens, durée ; client Anthropic instrumenté par
  [agent/observabilite.py](agent/observabilite.py)). Elles sont regroupées par fil Gmail (`thread_id`).
- **LangGraph Studio :** le graphe s'exécute en direct, nœud par nœud.

  ```bash
  langgraph dev --allow-blocking --no-reload
  ```

  Le lien Studio s'affiche dans le terminal. Un fil Studio correspond à un fil Gmail :
  - entrée : `{"expediteur", "objet", "corps"}` ;
  - pause de validation : reprendre avec `{"action": "approuver", "conseiller": "Khady"}` ;
  - réponse du client : nouvelle entrée dans le même fil.

  Gmail et Calendar y sont factices ([agent/studio.py](agent/studio.py)).

Sans ces variables, rien ne quitte la machine : seules les traces JSONL locales existent.

## Résultats

- **Traces analysées** ([traces/](traces/README.md)), toutes issues de lancements réels :
  - une demande de l'exercice 1 ;
  - une conversation complète, de la demande jusqu'à la visite confirmée ;
  - un échec analysé, puis corrigé.
- **Évaluation** ([eval/](eval/README.md)) : 15 emails de test. On y compare l'agent de
  l'exercice 1 et le pipeline sur le taux de réussite, les appels d'outils, les tokens et
  le temps ([conclusions](eval/conclusions_finales.md)).

## Tests

```bash
python -m pytest          # hors ligne : ni réseau, ni clé, ni .env
```

Serveur MCP : [mcp_server/README.md](mcp_server/README.md). Évaluation : [eval/README.md](eval/README.md).
