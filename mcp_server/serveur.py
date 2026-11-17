"""Serveur MCP du catalogue Sama Kër Immobilier (SDK Python MCP 2.x, classe MCPServer).

MCPServer est le nouveau nom de FastMCP depuis la version 2 du SDK.

Lancement, depuis la racine du dépôt :
    python -m mcp_server.serveur            # transport stdio (local)
    python -m mcp_server.serveur --http     # transport Streamable HTTP sur http://127.0.0.1:8000/mcp

En stdio, le serveur ne doit rien écrire avec print() : la sortie standard
sert à échanger les messages MCP avec le client.
"""

from __future__ import annotations

import sys
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from mcp_server.catalogue import CatalogueSQLite

HOTE = "127.0.0.1"
PORT = 8000

catalogue = CatalogueSQLite()

serveur = MCPServer(
    name="sama-ker-catalogue",
    instructions=(
        "Catalogue des biens à louer de l'agence Sama Kër Immobilier (Dakar). "
        "Ne propose jamais un bien qui n'a pas été renvoyé par rechercher_biens."
    ),
)


@serveur.tool()
def rechercher_biens(
    type: Annotated[
        Literal["appartement", "studio", "villa", "chambre", "bureau"] | None,
        Field(description="Type de bien. Un « F2/F3/F4 » est un appartement."),
    ] = None,
    quartier: Annotated[
        str | None,
        Field(description="Quartier de Dakar, ex. « Mermoz », « Point E », « Almadies »."),
    ] = None,
    loyer_max: Annotated[
        int | None,
        Field(description="Loyer mensuel maximal en F CFA, ex. 400000."),
    ] = None,
    pieces: Annotated[
        int | None,
        Field(description="Nombre de pièces exact : F3 = 3, F4 = 4."),
    ] = None,
) -> dict:
    """Cherche dans le catalogue de l'agence les biens à louer DISPONIBLES qui correspondent
    aux critères. Tous les critères sont optionnels ; n'en passe que ceux exprimés par le client.
    Renvoie {ok, biens: [...]} trié par loyer croissant ; une liste vide signifie qu'aucun bien
    ne correspond. En cas d'erreur : {ok: false, code, message}."""
    return catalogue.rechercher_biens(type=type, quartier=quartier, loyer_max=loyer_max, pieces=pieces)


@serveur.tool()
def detail_bien(
    bien_id: Annotated[str, Field(description="Référence du bien, ex. « SK-001 ».")],
) -> dict:
    """Renvoie la fiche complète d'un bien (adresse, description, disponibilité) à partir de
    sa référence, ex. « SK-001 ». N'utilise que des références obtenues par rechercher_biens.
    En cas d'erreur : {ok: false, code, message}."""
    return catalogue.detail_bien(bien_id)


def main() -> None:
    if "--http" in sys.argv:
        serveur.run("streamable-http", host=HOTE, port=PORT)
    else:
        serveur.run("stdio")


if __name__ == "__main__":
    main()