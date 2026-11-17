"""Petit client MCP de test : se connecte au serveur du catalogue et appelle ses outils.

Lancement, depuis la racine du dépôt :
    python -m mcp_server.essai_client           # lance le serveur en stdio et s'y connecte
    python -m mcp_server.essai_client --http    # se connecte au serveur déjà lancé en HTTP
"""

from __future__ import annotations

import asyncio
import sys

from mcp import Client, StdioServerParameters

URL_HTTP = "http://127.0.0.1:8000/mcp"


async def essayer(cible) -> None:
    async with Client(cible) as client:
        outils = await client.list_tools()
        print("Outils exposés :", [outil.name for outil in outils.tools])

        resultat = await client.call_tool(
            "rechercher_biens",
            {"type": "appartement", "quartier": "Mermoz", "pieces": 3, "loyer_max": 400000},
        )
        print("\nrechercher_biens (F3 à Mermoz, 400 000 F max) :")
        print(resultat.content[0].text)

        resultat = await client.call_tool("detail_bien", {"bien_id": "SK-099"})
        print("\ndetail_bien (SK-099, référence inexistante) :")
        print(resultat.content[0].text)


def main() -> None:
    if "--http" in sys.argv:
        cible = URL_HTTP
    else:
        cible = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.serveur"])
    asyncio.run(essayer(cible))


if __name__ == "__main__":
    main()