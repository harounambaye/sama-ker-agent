"""Disponibilités du client (« samedi matin », « mardi prochain », « cette semaine »)
-> fenêtre de recherche réelle, au fuseau de Dakar, jamais dans le passé.

Déterministe et testable : la date de référence est passée en argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from contracts import FUSEAU, HEURE_FERMETURE, HEURE_OUVERTURE, JOURS_OUVRES

DAKAR = ZoneInfo(FUSEAU)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PLAGES = {"matin": (HEURE_OUVERTURE, 12), "apres_midi": (14, HEURE_FERMETURE),
          "journee": (HEURE_OUVERTURE, HEURE_FERMETURE)}
DELAI_MIN = timedelta(hours=2)   # pas de visite proposée moins de 2 h à l'avance


@dataclass(frozen=True)
class Fenetre:
    debut: datetime
    fin: datetime
    libelle: str                  # « samedi 21 novembre, matin »
    ajustement: str | None = None  # ce qui a été changé par rapport à la demande
    heure: str | None = None       # heure précise demandée, « HH:MM »


def _a(jour: date, heure: int) -> datetime:
    return datetime.combine(jour, time(heure), tzinfo=DAKAR)


def _libelle(jour: date, plage: str) -> str:
    noms_mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                 "septembre", "octobre", "novembre", "décembre"]
    texte = f"{JOURS[jour.weekday()]} {jour.day} {noms_mois[jour.month - 1]}"
    return texte + {"matin": ", matin", "apres_midi": ", après-midi", "journee": ""}[plage]


def _prochain(reference: date, jour_semaine: int, semaine_prochaine: bool) -> date:
    """Prochaine occurrence STRICTEMENT après la date de référence ; « prochain » : dans
    la semaine calendaire suivante (lundi à dimanche)."""
    if semaine_prochaine:
        lundi_suivant = reference + timedelta(days=7 - reference.weekday())
        return lundi_suivant + timedelta(days=jour_semaine)
    ecart = (jour_semaine - reference.weekday()) % 7 or 7
    return reference + timedelta(days=ecart)


def fenetre(disponibilites: dict | None, maintenant: datetime) -> Fenetre:
    """Fenêtre où chercher des créneaux. `maintenant` : date de réception ou heure actuelle,
    la plus récente des deux (on ne propose jamais un créneau passé)."""
    d = disponibilites or {}
    maintenant = maintenant.astimezone(DAKAR)
    plus_tot = maintenant + DELAI_MIN
    plage = d.get("plage") or "journee"
    h_debut, h_fin = PLAGES[plage]
    jour, ajustement = d.get("jour"), None

    if jour == "dimanche":
        jour, ajustement = "lundi", "pas de visite le dimanche : créneaux proposés le lundi suivant"

    if jour in JOURS:
        j = _prochain(maintenant.date(), JOURS.index(jour), bool(d.get("semaine_prochaine")))
        return Fenetre(_a(j, h_debut), _a(j, h_fin), _libelle(j, plage), ajustement, d.get("heure"))

    if jour == "demain":
        j = maintenant.date() + timedelta(days=1)
        if j.weekday() not in JOURS_OUVRES:
            j += timedelta(days=1)
            ajustement = "pas de visite le dimanche : créneaux proposés le lundi"
        return Fenetre(_a(j, h_debut), _a(j, h_fin), _libelle(j, plage), ajustement, d.get("heure"))

    # « cette semaine » ou rien de précis : du plus tôt possible à la fin de la semaine
    # (samedi), ou sur les 7 prochains jours si la semaine est déjà finie / non précisée.
    debut = max(plus_tot, _a(maintenant.date(), h_debut))
    if jour == "semaine" and not d.get("semaine_prochaine"):
        samedi = maintenant.date() + timedelta(days=(5 - maintenant.weekday()) % 7)
        fin = _a(samedi, h_fin)
        if fin - debut >= timedelta(hours=1):
            return Fenetre(debut, fin, "cette semaine", None, d.get("heure"))
        ajustement = "la semaine est terminée : créneaux proposés la semaine prochaine"
    if d.get("semaine_prochaine"):
        lundi = maintenant.date() + timedelta(days=7 - maintenant.weekday())
        return Fenetre(_a(lundi, h_debut), _a(lundi + timedelta(days=5), h_fin),
                       "la semaine prochaine", ajustement, d.get("heure"))
    return Fenetre(debut, _a(debut.date() + timedelta(days=7), h_fin),
                   "les prochains jours", ajustement, d.get("heure"))


def elargir(f: Fenetre) -> Fenetre:
    """Aucun créneau libre : on cherche sur les 7 jours qui suivent la fenêtre demandée."""
    debut = _a(f.fin.date() + timedelta(days=1), HEURE_OUVERTURE)
    return Fenetre(debut, _a(debut.date() + timedelta(days=6), HEURE_FERMETURE),
                   "les jours suivants", f"aucun créneau libre {f.libelle} : autres dates proposées")


def libelle_creneau(debut_iso: str) -> str:
    """« samedi 21 novembre à 9 h 00 »."""
    d = datetime.fromisoformat(debut_iso).astimezone(DAKAR)
    return f"{_libelle(d.date(), 'journee')} à {d.hour} h {d.minute:02d}"
