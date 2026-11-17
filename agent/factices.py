"""Messagerie et agenda factices, conformes à contracts.Messagerie et contracts.Agenda.

TEMPORAIRES : ils permettent de construire et démontrer la validation humaine et
le pipeline avant la PR Google de Papa. Leur état peut être enregistré dans un
fichier JSON, pour qu'un conseiller valide depuis un autre processus.

`panne = True` simule une brique indisponible (sonde et écritures en erreur).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts import (
    CONSEILLERS, DUREE_VISITE_MIN, FUSEAU, HEURE_FERMETURE, HEURE_OUVERTURE,
    JOURS_OUVRES, Agenda, EtatMessage, Messagerie, erreur, id_evenement,
)

DAKAR = ZoneInfo(FUSEAU)
DUREE = timedelta(minutes=DUREE_VISITE_MIN)


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


def _date(iso: str) -> datetime:
    d = datetime.fromisoformat(iso)
    return d.replace(tzinfo=DAKAR) if d.tzinfo is None else d.astimezone(DAKAR)


def _creneaux_du_jour(jour: datetime) -> list[datetime]:
    """Débuts de visite d'une journée ouvrée : 9h00, 9h45, ... dernier fini à 18h00."""
    if jour.weekday() not in JOURS_OUVRES:
        return []
    debut = jour.replace(hour=HEURE_OUVERTURE, minute=0, second=0, microsecond=0)
    fermeture = jour.replace(hour=HEURE_FERMETURE, minute=0, second=0, microsecond=0)
    creneaux = []
    while debut + DUREE <= fermeture:
        creneaux.append(debut)
        debut += DUREE
    return creneaux


class AgendaFactice(_Persistant, Agenda):
    def _vide(self) -> dict:
        return {"compteur": 0, "evenements": {}}

    @property
    def evenements(self) -> dict[str, dict]:
        return dict(self._d["evenements"])

    def _libre(self, conseiller: str, debut: datetime, sauf: str | None = None) -> bool:
        fin = debut + DUREE
        for ev_id, ev in self._d["evenements"].items():
            if ev_id == sauf or ev["conseiller"] != conseiller:
                continue
            if _date(ev["debut"]) < fin and debut < _date(ev["fin"]):
                return False
        return True

    @staticmethod
    def _conforme(debut: datetime) -> bool:
        return debut in _creneaux_du_jour(debut)

    def lister_creneaux_libres(self, conseiller, debut, fin):
        if self.panne:
            return erreur("INDISPONIBLE", "Calendar injoignable (panne simulée).")
        if conseiller is not None and conseiller not in CONSEILLERS:
            return erreur("ARGUMENT_INVALIDE", f"Conseiller inconnu : {conseiller}.")
        try:
            t0, t1 = _date(debut), _date(fin)
        except ValueError:
            return erreur("ARGUMENT_INVALIDE", "debut et fin doivent être des dates ISO 8601.")
        cibles = [conseiller] if conseiller else list(CONSEILLERS)
        creneaux = []
        jour = t0.replace(hour=0, minute=0, second=0, microsecond=0)
        while jour <= t1:
            for c in _creneaux_du_jour(jour):
                if c < t0 or c + DUREE > t1:
                    continue
                for nom in cibles:
                    if self._libre(nom, c):
                        creneaux.append({"conseiller": nom, "debut": c.isoformat(),
                                         "fin": (c + DUREE).isoformat()})
            jour += timedelta(days=1)
        return {"ok": True, "creneaux": creneaux}

    def creer_visite(self, conseiller, debut, bien_id, adresse, client_nom,
                     client_email, fil_id):
        if self.panne:
            return erreur("INDISPONIBLE", "Calendar injoignable (panne simulée).")
        if conseiller not in CONSEILLERS:
            return erreur("ARGUMENT_INVALIDE", f"Conseiller inconnu : {conseiller}.")
        d = _date(debut)
        ev_id = id_evenement(fil_id, d.isoformat())
        if ev_id in self._d["evenements"]:   # même fil, même créneau : pas de doublon
            return {"ok": True, "evenement_id": ev_id, "deja_existante": True}
        if not self._conforme(d):
            return erreur("CRENEAU_INDISPONIBLE",
                          "Hors règles de l'agence (lundi-samedi, 9h-18h, 45 min).")
        if not self._libre(conseiller, d):   # revérification juste avant l'écriture
            return erreur("CRENEAU_INDISPONIBLE", "Créneau pris entre-temps : proposer d'autres créneaux.")
        self._d["evenements"][ev_id] = {
            "conseiller": conseiller, "debut": d.isoformat(), "fin": (d + DUREE).isoformat(),
            "bien_id": bien_id, "adresse": adresse, "client_nom": client_nom,
            "client_email": client_email, "fil_id": fil_id,
            "titre": f"Visite {bien_id} - {client_nom}",
        }
        self._sauver()
        return {"ok": True, "evenement_id": ev_id, "deja_existante": False}

    def deplacer_visite(self, evenement_id, nouveau_debut):
        if self.panne:
            return erreur("INDISPONIBLE", "Calendar injoignable (panne simulée).")
        ev = self._d["evenements"].get(evenement_id)
        if ev is None:
            return erreur("INTROUVABLE", f"Aucune visite {evenement_id}.")
        d = _date(nouveau_debut)
        if not self._conforme(d) or not self._libre(ev["conseiller"], d, sauf=evenement_id):
            return erreur("CRENEAU_INDISPONIBLE", "Nouveau créneau indisponible.")
        ev["debut"], ev["fin"] = d.isoformat(), (d + DUREE).isoformat()
        self._sauver()
        return {"ok": True}

    def annuler_visite(self, evenement_id):
        if self.panne:
            return erreur("INDISPONIBLE", "Calendar injoignable (panne simulée).")
        if self._d["evenements"].pop(evenement_id, None) is None:
            return erreur("INTROUVABLE", f"Aucune visite {evenement_id}.")
        self._sauver()
        return {"ok": True}
