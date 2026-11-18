# Serveur MCP du catalogue Sama Kër Immobilier

Serveur MCP qui expose le catalogue de l'agence : **30 biens à louer fictifs à Dakar**,
stockés dans une base SQLite. N'importe quel client MCP (agent, inspecteur MCP, autre
équipe) peut chercher des biens, lire leur fiche, vérifier l'état du catalogue et lire les
informations de l'agence.

- SDK : `mcp` 2.x pour Python (classe `MCPServer`, nouveau nom de `FastMCP`)
- Transports : **stdio** (local) et **Streamable HTTP** (`http://127.0.0.1:8000/mcp`)
- Format des données : celui de `contracts.py` (`Bien`, `Erreur`, `Etat`)

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `creer_catalogue.py` | Crée la base SQLite avec les 30 biens (relançable, résultat identique) |
| `catalogue.py` | Les outils : `rechercher_biens`, `detail_bien`, `verifier_etat` |
| `agence.py` | La fiche de l'agence (horaires, zones, conditions) |
| `serveur.py` | Le serveur MCP qui expose les outils et la ressource |
| `essai_client.py` | Petit client de test qui se connecte au serveur et appelle ses outils |

## Démarrage

Depuis la racine du dépôt, avec l'environnement virtuel activé :

```bash
python -m pip install -r requirements.txt
cp .env.example .env                    # Windows : Copy-Item .env.example .env
python -m mcp_server.creer_catalogue    # crée data/catalogue.sqlite (30 biens)
```

La base est créée à l'emplacement de la variable `CATALOGUE_DB` du `.env`
(par défaut `data/catalogue.sqlite`). Elle n'est pas versionnée : on la recrée avec le script.
Aucune clé ni aucun identifiant n'est nécessaire pour le serveur.

## Lancer le serveur

```bash
python -m mcp_server.serveur            # stdio : le client lance le serveur lui-même
python -m mcp_server.serveur --http     # Streamable HTTP sur http://127.0.0.1:8000/mcp
```

En HTTP, le serveur n'écoute que sur `127.0.0.1` : il n'est joignable que depuis
l'ordinateur où il tourne.

## Se brancher sur le serveur

### Depuis Python (SDK `mcp` 2.x)

```python
import asyncio
import sys
from mcp import Client, StdioServerParameters

async def main():
    # stdio : le client lance le serveur
    serveur = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.serveur"])
    # ou HTTP, si le serveur tourne déjà avec --http :
    # serveur = "http://127.0.0.1:8000/mcp"
    async with Client(serveur) as client:
        resultat = await client.call_tool(
            "rechercher_biens",
            {"type": "appartement", "quartier": "Mermoz", "pieces": 3, "loyer_max": 400000},
        )
        print(resultat.content[0].text)

asyncio.run(main())
```

En stdio, la commande doit être lancée depuis la racine du dépôt.

### Depuis l'inspecteur MCP

```bash
# stdio
npx @modelcontextprotocol/inspector python -m mcp_server.serveur
# HTTP : lancer d'abord le serveur avec --http, puis
npx @modelcontextprotocol/inspector
# et choisir « Streamable HTTP » avec l'URL http://127.0.0.1:8000/mcp
```

Sous Windows, remplacer `python` par `.venv\Scripts\python.exe`.

## Outils

Toutes les réponses sont des objets JSON. En cas d'erreur, un outil ne plante jamais :
il renvoie `{"ok": false, "code": "...", "message": "..."}`, avec un message qui dit
comment corriger.

### `rechercher_biens`

Cherche les biens **disponibles** qui respectent tous les critères donnés.
Tous les arguments sont facultatifs.

| Argument | Type | Description |
|---|---|---|
| `type` | texte | `appartement`, `studio`, `villa`, `chambre` ou `bureau`. Un F2, F3, F4 est un `appartement`. |
| `quartier` | texte | Quartier de Dakar. Comparé sans tenir compte des accents, de la ligature œ, des majuscules ni des tirets : « sacre coeur » trouve « Sacré-Cœur ». |
| `loyer_max` | entier | Loyer mensuel maximal en F CFA, par exemple `400000`. |
| `pieces` | entier | Nombre de pièces **exact** : F3 = `3`. |

Réponse : `{"ok": true, "biens": [...]}`, triée par loyer croissant.
**Une liste vide signifie qu'aucun bien ne correspond.**

Exemple : un F3 à Mermoz à 400 000 F maximum.

```json
{"type": "appartement", "quartier": "Mermoz", "pieces": 3, "loyer_max": 400000}
```

```json
{
  "ok": true,
  "biens": [
    {
      "id": "SK-001",
      "type": "appartement",
      "quartier": "Mermoz",
      "loyer_fcfa": 350000,
      "pieces": 3,
      "adresse": "Rue MZ-12, Mermoz, Dakar",
      "disponible": true,
      "description": "F3 lumineux, 2 chambres, balcon."
    }
  ]
}
```

### `detail_bien`

Renvoie la fiche complète d'un bien à partir de sa référence.

| Argument | Type | Description |
|---|---|---|
| `bien_id` | texte, **obligatoire** | Référence du bien, par exemple `SK-001`. Les espaces et les minuscules sont acceptés. |

Réponse : `{"ok": true, "bien": {...}}`.

Exemple d'erreur, avec `{"bien_id": "SK-099"}` :

```json
{
  "ok": false,
  "code": "INTROUVABLE",
  "message": "Aucun bien de référence SK-099. Utilise une référence renvoyée par rechercher_biens."
}
```

### `verifier_etat`

Sans argument, ne modifie rien. Vérifie que la base s'ouvre et contient les 30 biens.

Réponse : `{"ok": true, "latence_ms": 1}`, ou une erreur `INDISPONIBLE`
(base absente ou illisible) ou `INTERNE` (nombre de biens incorrect).
Dans les deux cas, le message indique la commande qui répare : `python -m mcp_server.creer_catalogue`.

### Codes d'erreur

| Code | Quand |
|---|---|
| `ARGUMENT_INVALIDE` | Type inconnu, loyer ou nombre de pièces négatif, référence vide |
| `INTROUVABLE` | Référence de bien inexistante |
| `INDISPONIBLE` | Base absente ou illisible : ne proposer aucun bien de mémoire |
| `INTERNE` | Le catalogue ne contient pas les 30 biens attendus |

## Ressource

| URI | Format | Contenu |
|---|---|---|
| `agence://informations` | Markdown | Horaires de visite (lundi au samedi, 9 h à 18 h, visites de 45 min, fuseau Africa/Dakar), zones couvertes, conditions de location |

Les horaires viennent de `contracts.py`, comme ceux de l'intégration Google Calendar.
Les conditions de location sont fictives.

## Le catalogue

- 30 biens, références `SK-001` à `SK-030`, dont 4 indisponibles (`SK-003`, `SK-015`, `SK-022`, `SK-029`).
- `SK-001` à `SK-010` sont identiques au catalogue factice de l'agent : les dix demandes de
  `agent/critere_ex1.py` gardent les mêmes résultats attendus.
- Quartiers couverts : Almadies, Fann, Grand Yoff, Liberté 6, Mermoz, Ngor, Ouakam,
  Parcelles Assainies, Plateau, Point E, Sacré-Cœur, Yoff.

## Vérifier le serveur

```bash
python -m mcp_server.essai_client           # stdio
python -m mcp_server.essai_client --http    # HTTP (serveur lancé avec --http)
```

Sortie attendue : les 3 outils, `verifier_etat` à `ok`, la ressource `agence://informations`,
le bien `SK-001` pour un F3 à Mermoz à 400 000 F maximum, et l'erreur `INTROUVABLE` pour `SK-099`.
