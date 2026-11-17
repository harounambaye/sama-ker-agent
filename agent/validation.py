"""Validation humaine : ce qu'on soumet au conseiller, sa décision, et l'écriture.

Règle de l'agence : aucun email ne part et aucune visite n'est créée, déplacée ou
annulée sans l'accord d'un conseiller. Le modèle n'a aucun outil d'écriture :
seule `appliquer()` écrit, et le graphe ne l'appelle qu'après une décision
« approuver » ou « modifier » obtenue par interrupt().
"""

from __future__ import annotations

from typing import Literal, TypedDict

from contracts import Agenda, Messagerie, erreur

TypeEcriture = Literal["envoyer_brouillon", "creer_visite", "deplacer_visite", "annuler_visite"]
BRIQUE: dict[str, str] = {
    "envoyer_brouillon": "gmail",
    "creer_visite": "calendar",
    "deplacer_visite": "calendar",
    "annuler_visite": "calendar",
}


class Proposition(TypedDict, total=False):
    type: TypeEcriture
    arguments: dict          # arguments exacts de la fonction du contrat
    resume: str              # ce que le conseiller lit pour décider
    texte: str               # corps du brouillon, modifiable (envoyer_brouillon)
    fil_id: str


class Decision(TypedDict, total=False):
    action: Literal["approuver", "modifier", "refuser"]
    texte: str               # nouveau texte si action == "modifier"
    motif: str               # raison si action == "refuser"
    conseiller: str


def controler(decision: object, proposition: Proposition) -> str | None:
    """Renvoie un message d'erreur si la décision est inexploitable, sinon None."""
    if not isinstance(decision, dict):
        return "Décision illisible."
    action = decision.get("action")
    if action not in ("approuver", "modifier", "refuser"):
        return f"Action inconnue : {action!r} (approuver, modifier ou refuser)."
    if not decision.get("conseiller"):
        return "Le nom du conseiller qui valide est obligatoire."
    if action == "modifier":
        if proposition["type"] != "envoyer_brouillon":
            return "Seul un brouillon d'email peut être modifié ; refuser puis reformuler."
        if not (decision.get("texte") or "").strip():
            return "Texte modifié vide."
    return None


def appliquer(proposition: Proposition, decision: Decision,
              agenda: Agenda, messagerie: Messagerie) -> dict:
    """Exécute l'écriture validée. Ne lève jamais : renvoie le format commun."""
    if decision.get("action") not in ("approuver", "modifier"):
        return erreur("ARGUMENT_INVALIDE", "Aucune écriture sans approbation.")
    t, args = proposition["type"], proposition["arguments"]

    if t == "envoyer_brouillon":
        brouillon_id = args["brouillon_id"]
        if decision["action"] == "modifier":
            # le texte validé est celui du conseiller : nouveau brouillon dans le même fil
            nouveau = messagerie.creer_brouillon(proposition["fil_id"], decision["texte"])
            if not nouveau.get("ok"):
                return nouveau
            brouillon_id = nouveau["brouillon_id"]
        resultat = messagerie.envoyer_brouillon(brouillon_id)
        return {**resultat, "brouillon_id": brouillon_id} if resultat.get("ok") else resultat
    if t == "creer_visite":
        return agenda.creer_visite(**args)
    if t == "deplacer_visite":
        return agenda.deplacer_visite(**args)
    if t == "annuler_visite":
        return agenda.annuler_visite(**args)
    return erreur("ARGUMENT_INVALIDE", f"Type d'écriture inconnu : {t}.")
