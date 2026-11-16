"""État des briques : l'agent vérifie que ses outils répondent avant de s'en servir.

Chaque brique expose verifier_etat() -> {"ok": True, "latence_ms": int} ou une Erreur.
La vérification est faite par le code, jamais par le modèle : elle ne coûte aucun token.

Quand vérifier (contrat d'équipe) :
  1. au démarrage, sur toutes les briques : une brique en erreur bloque le lancement ;
  2. avant chaque email, résultat conservé TTL secondes ;
  3. après une erreur d'outil, en forçant (panne passagère ou brique indisponible ?) ;
  4. juste avant une écriture validée, en forçant.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from contracts import erreur

Verification = Callable[[], dict]


class VerificateurEtat:
    def __init__(
        self,
        briques: dict[str, Verification],
        ttl_s: float = 60.0,
        delai_s: float = 10.0,
        horloge: Callable[[], float] = time.monotonic,
    ):
        self._briques = briques
        self._ttl = ttl_s
        self._delai = delai_s
        self._horloge = horloge
        self._cache: dict[str, tuple[float, dict]] = {}
        self._pool = ThreadPoolExecutor(max_workers=max(1, len(briques)))

    @property
    def noms(self) -> list[str]:
        return list(self._briques)

    def _sonder(self, nom: str) -> dict:
        # Un thread dédié par sonde : une brique bloquée ne retient aucun thread
        # du pool, et l'attente est bornée par le délai.
        t0 = time.perf_counter()
        boite: dict = {}

        def cible() -> None:
            try:
                boite["resultat"] = self._briques[nom]()
            except Exception as e:  # une sonde ne doit jamais faire tomber l'agent
                boite["exception"] = e

        fil = threading.Thread(target=cible, name=f"sonde-{nom}", daemon=True)
        fil.start()
        fil.join(self._delai)
        if fil.is_alive():
            return erreur("DELAI_DEPASSE", f"{nom} n'a pas répondu en {self._delai:g} s.")
        if "exception" in boite:
            e = boite["exception"]
            return erreur("INDISPONIBLE", f"{nom} : {type(e).__name__}: {e}")
        resultat = boite.get("resultat")
        if not isinstance(resultat, dict) or "ok" not in resultat:
            return erreur("INTERNE", f"{nom} : réponse de verifier_etat non conforme.")
        if resultat["ok"] and "latence_ms" not in resultat:
            resultat = {**resultat, "latence_ms": round((time.perf_counter() - t0) * 1000)}
        return resultat

    def verifier(self, *noms: str, forcer: bool = False) -> dict[str, dict]:
        """Vérifie les briques demandées (toutes par défaut), en parallèle.

        forcer=False réutilise un résultat de moins de TTL secondes ;
        forcer=True interroge la brique (après une erreur, avant une écriture).
        """
        cibles = list(noms) or self.noms
        if inconnues := [n for n in cibles if n not in self._briques]:
            raise KeyError(f"Briques inconnues : {inconnues}")
        maintenant = self._horloge()
        resultats: dict[str, dict] = {}
        a_sonder = []
        for nom in cibles:
            en_cache = self._cache.get(nom)
            if not forcer and en_cache and maintenant - en_cache[0] < self._ttl:
                resultats[nom] = en_cache[1]
            else:
                a_sonder.append(nom)
        for nom, res in zip(a_sonder, self._pool.map(self._sonder, a_sonder)):
            self._cache[nom] = (self._horloge(), res)
            resultats[nom] = res
        return {nom: resultats[nom] for nom in cibles}

    def disponibles(self, *noms: str, forcer: bool = False) -> bool:
        return all(r["ok"] for r in self.verifier(*noms, forcer=forcer).values())


def rapport(resultats: dict[str, dict]) -> str:
    """Tableau lisible de l'état des briques."""
    lignes = []
    for nom, r in resultats.items():
        if r["ok"]:
            detail = f"{r['latence_ms']} ms" + (f" · {r['mode']}" if "mode" in r else "")
            lignes.append(f"  ok      {nom:<10} {detail}")
        else:
            lignes.append(f"  ERREUR  {nom:<10} [{r['code']}] {r['message']}")
    return "\n".join(lignes)


def main() -> None:
    """python -m agent.etat : état des quatre briques, code de sortie 1 si l'une est en erreur."""
    import sys

    from agent import config
    from agent.briques import sondes
    from agent.catalogue_factice import CatalogueFactice

    cfg = config.charger()
    resultats = VerificateurEtat(sondes(cfg, CatalogueFactice())).verifier()
    print(f"État des briques (modèle : {cfg.model})\n{rapport(resultats)}")
    tout_ok = all(r["ok"] for r in resultats.values())
    print("\nok" if tout_ok else "\nAu moins une brique est indisponible.")
    sys.exit(0 if tout_ok else 1)


if __name__ == "__main__":
    main()
