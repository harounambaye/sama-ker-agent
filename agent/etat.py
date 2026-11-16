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

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse
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
        t0 = time.perf_counter()
        futur = self._pool.submit(self._briques[nom])
        try:
            resultat = futur.result(timeout=self._delai)
        except DelaiDepasse:
            return erreur("DELAI_DEPASSE", f"{nom} n'a pas répondu en {self._delai:.0f} s.")
        except Exception as e:  # une sonde ne doit jamais faire tomber l'agent
            return erreur("INDISPONIBLE", f"{nom} : {type(e).__name__}: {e}")
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
