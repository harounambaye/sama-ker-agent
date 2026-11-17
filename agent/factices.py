"""Messagerie et agenda factices, conformes à contracts.Messagerie et contracts.Agenda.

TEMPORAIRES : ils permettent de construire et démontrer la validation humaine et
le pipeline avant la PR Google de Papa. Leur état peut être enregistré dans un
fichier JSON, pour qu'un conseiller valide depuis un autre processus.

`panne = True` simule une brique indisponible (sonde et écritures en erreur).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from contracts import EtatMessage, Messagerie, erreur


class _Persistant:
    def __init__(self, chemin: str | Path | None = None):
        self._chemin = Path(chemin) if chemin else None
        self.panne = False
        if self._chemin and self._chemin.exists():
            self._d = json.loads(self._chemin.read_text(encoding="utf-8"))
        else:
            self._d = self._vide()

    def _vide(self) -> dict:
        raise NotImplementedError

    def _sauver(self) -> None:
        if self._chemin:
            self._chemin.parent.mkdir(parents=True, exist_ok=True)
            self._chemin.write_text(json.dumps(self._d, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

    def _nouvel_id(self, prefixe: str) -> str:
        self._d["compteur"] += 1
        return f"{prefixe}{self._d['compteur']:04d}"

    def verifier_etat(self) -> dict:
        if self.panne:
            return erreur("INDISPONIBLE", f"{type(self).__name__} : panne simulée.")
        return {"ok": True, "latence_ms": 0, "mode": "factice"}


class MessagerieFactice(_Persistant, Messagerie):
    def _vide(self) -> dict:
        return {"compteur": 0, "messages": {}, "brouillons": {}, "envoyes": []}

    # -- hors contrat : simule la réception d'un email -------------------- #
    def recevoir(self, expediteur: str, sujet: str, corps: str,
                 fil_id: str | None = None) -> dict:
        message_id = self._nouvel_id("m")
        demande = {
            "message_id": message_id,
            "fil_id": fil_id or f"fil-{message_id}",
            "expediteur": expediteur,
            "sujet": sujet,
            "corps": corps,
            "recu_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "etat": "a_traiter",
        }
        self._d["messages"][message_id] = demande
        self._sauver()
        return {k: v for k, v in demande.items() if k != "etat"}

    @property
    def envoyes(self) -> list[dict]:
        return list(self._d["envoyes"])

    def etat_message(self, message_id: str) -> str:
        return self._d["messages"][message_id]["etat"]

    # -- contrat ----------------------------------------------------------- #
    def lire_demandes(self):
        if self.panne:
            return erreur("INDISPONIBLE", "Gmail injoignable (panne simulée).")
        demandes = [{k: v for k, v in m.items() if k != "etat"}
                    for m in self._d["messages"].values() if m["etat"] == "a_traiter"]
        return {"ok": True, "demandes": demandes}

    def creer_brouillon(self, fil_id, texte):
        if self.panne:
            return erreur("INDISPONIBLE", "Gmail injoignable (panne simulée).")
        dans_le_fil = [m for m in self._d["messages"].values() if m["fil_id"] == fil_id]
        if not dans_le_fil:
            return erreur("INTROUVABLE", f"Aucun fil {fil_id}.")
        dernier = dans_le_fil[-1]
        brouillon_id = self._nouvel_id("d")
        self._d["brouillons"][brouillon_id] = {
            "fil_id": fil_id, "a": dernier["expediteur"],
            "sujet": "Re: " + dernier["sujet"], "texte": texte,
        }
        self._sauver()
        return {"ok": True, "brouillon_id": brouillon_id}

    def envoyer_brouillon(self, brouillon_id):
        if self.panne:
            return erreur("INDISPONIBLE", "Gmail injoignable (panne simulée).")
        brouillon = self._d["brouillons"].pop(brouillon_id, None)
        if brouillon is None:
            return erreur("INTROUVABLE", f"Aucun brouillon {brouillon_id} (déjà envoyé ?).")
        self._d["envoyes"].append({"brouillon_id": brouillon_id, **brouillon})
        self._sauver()
        return {"ok": True}

    def changer_libelle(self, message_id, etat: EtatMessage):
        if self.panne:
            return erreur("INDISPONIBLE", "Gmail injoignable (panne simulée).")
        if message_id not in self._d["messages"]:
            return erreur("INTROUVABLE", f"Aucun message {message_id}.")
        self._d["messages"][message_id]["etat"] = etat
        self._sauver()
        return {"ok": True}
