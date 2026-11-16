"""Traces : un fichier JSONL par traitement, une ligne par événement.

Chaque appel d'outil y figure avec ses arguments, son résultat et sa durée ;
chaque appel au modèle avec ses tokens et sa raison d'arrêt.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts import FUSEAU


class Trace:
    def __init__(self, dossier: str, etiquette: str = "", verbeux: bool = False):
        self.run_id = uuid.uuid4().hex[:8]
        horodatage = datetime.now(ZoneInfo(FUSEAU)).strftime("%Y%m%d-%H%M%S")
        nom = f"{horodatage}_{etiquette + '_' if etiquette else ''}{self.run_id}.jsonl"
        Path(dossier).mkdir(parents=True, exist_ok=True)
        self.chemin = Path(dossier) / nom
        self.verbeux = verbeux
        self._t0 = time.perf_counter()

    def evenement(self, type_: str, **donnees) -> None:
        ligne = {
            "t_ms": round((time.perf_counter() - self._t0) * 1000),
            "run_id": self.run_id,
            "type": type_,
            **donnees,
        }
        with self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False, default=str) + "\n")
        if self.verbeux:
            self._afficher(type_, donnees)

    @staticmethod
    def _afficher(type_: str, d: dict) -> None:
        if type_ == "appel_outil":
            etat = "ok" if d["resultat"].get("ok") else f"ERREUR {d['resultat'].get('code')}"
            print(f"  -> {d['outil']}({json.dumps(d['arguments'], ensure_ascii=False)}) "
                  f"[{etat}, {d['duree_ms']} ms]")
        elif type_ == "appel_modele":
            print(f"  [modèle] étape {d['etape']} · {d['stop_reason']} · "
                  f"in={d['tokens_entree']} out={d['tokens_sortie']} "
                  f"cache_lu={d['tokens_cache_lus']} · {d['duree_ms']} ms")
        else:
            print(f"  [{type_}] {json.dumps(d, ensure_ascii=False, default=str)[:200]}")
