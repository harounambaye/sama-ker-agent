"""Pipeline complet de l'exercice 5 : un email entre, une réponse validée sort.

    START -> trier (modèle : catégorie + besoin, sortie typée)
      transmettre ........ hors périmètre / injection / échec -> libellé « transmis »
      demander_precision . rediger -> brouillon -> VALIDER -> envoi
      repondre_agence .... rediger (fiche agence MCP) -> brouillon -> VALIDER -> envoi
      proposer ........... rechercher (catalogue // agenda) -> rediger -> brouillon -> VALIDER -> envoi
      confirmer .......... choisir_visite -> VALIDER creer_visite -> ecrire
                             ok : rediger confirmation -> brouillon -> VALIDER -> envoi
                             créneau pris entre-temps : nouveaux créneaux -> brouillon -> VALIDER

Le modèle COMPREND (tri) et RÉDIGE ; le CODE cherche, choisit les créneaux, contrôle
et décide. Aucune écriture (email ou agenda) sans passage par `valider` (interrupt).
L'état est gardé par fil Gmail : quand le client répond, les créneaux proposés sont
retrouvés dans le checkpointer.
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from typing import Callable, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.config import Config
from agent.conversation import situation
from agent.dates import DAKAR, JOURS, fenetre, libelle_creneau
from agent.etat import VerificateurEtat, rapport
from agent.memoire import config_fil
from agent.modele import client_par_defaut
from agent.outils import BoiteAOutils
from agent.recherche import rassembler
from agent.redaction import rediger
from agent.traces import Trace
from agent.tri import analyser, parcours
from agent.validation import BRIQUE, Decision, Proposition, appliquer, controler
from contracts import CONSEILLERS, Agenda, Bien, Creneau, Demande, Messagerie

URI_AGENCE = "agence://informations"

# Décision exposée pour l'évaluation (eval/emails_test.json, decisions_possibles).
DECISION = {"proposer": "repondre", "repondre_agence": "repondre",
            "demander_precision": "demander_precision", "transmettre": "transmettre",
            "confirmer": "creer_visite"}


class EtatPipeline(TypedDict, total=False):
    # email en cours
    demande: Demande
    fil_id: str
    message_id: str
    expediteur: str
    # compréhension et décision
    analyse: dict | None
    parcours: str | None
    decision_agent: str | None
    note: str
    faits: dict | None
    brouillon_texte: str | None
    # mémoire du fil, gardée d'un email à l'autre
    creneaux_proposes: list[Creneau]
    biens_proposes: list[Bien]
    creneau_choisi: Creneau | None
    visite: dict | None
    # validation humaine
    proposition: Proposition | None
    decision: Decision | None
    incident: str | None
    issue: str | None
    # mesures de l'email en cours
    tokens_entree: int
    tokens_sortie: int
    appels_modele: int
    appels_outils: int


def _compter(etat: EtatPipeline, r: dict) -> dict:
    return {"tokens_entree": etat.get("tokens_entree", 0) + r.get("tokens_entree", 0),
            "tokens_sortie": etat.get("tokens_sortie", 0) + r.get("tokens_sortie", 0),
            "appels_modele": etat.get("appels_modele", 0) + 1}


def fiche_agence(outils: BoiteAOutils) -> dict:
    """Ressource MCP de l'agence ; en mode factice, la même fiche lue localement."""
    if hasattr(outils, "lire_ressource"):
        return outils.lire_ressource(URI_AGENCE)
    from mcp_server.agence import informations_agence
    return {"ok": True, "texte": informations_agence()}


def manquant(analyse: dict) -> list[str]:
    b, d = analyse["besoin"], analyse["disponibilites"]
    liste = []
    if not b["quartier"]:
        liste.append("le quartier souhaité")
    if b["loyer_max"] is None:
        liste.append("le budget mensuel maximal")
    if b["type"] is None and b["pieces"] is None:
        liste.append("le type de bien ou le nombre de pièces")
    if not d["jour"]:
        liste.append("les disponibilités pour une visite")
    return liste


def construire_pipeline(
    cfg: Config,
    outils: BoiteAOutils,
    agenda: Agenda,
    messagerie: Messagerie,
    verificateur: VerificateurEtat,
    trace: Trace,
    checkpointer,
    client: anthropic.Anthropic | None = None,
    horloge: Callable[[], datetime] = lambda: datetime.now(DAKAR),
):
    client = client or client_par_defaut()

    def maintenant(etat: EtatPipeline) -> datetime:
        recu = etat["demande"].get("recu_le")
        instant = horloge()
        return max(instant, datetime.fromisoformat(recu)) if recu else instant

    # ------------------------------------------------------------- tri --- #
    def trier(etat: EtatPipeline) -> dict:
        if not verificateur.disponibles("gmail"):
            incident = rapport(verificateur.verifier("gmail"))
            trace.evenement("incident", fil_id=etat["fil_id"], etape="debut", detail=incident)
            return {"issue": "reporte", "incident": incident}
        deja = [libelle_creneau(c["debut"]) for c in etat.get("creneaux_proposes") or []]
        r = analyser(client, cfg, etat["demande"], trace, deja)
        maj = _compter(etat, r)
        if not r["ok"]:
            return maj | {"parcours": "transmettre", "decision_agent": "transmettre",
                          "note": f"Tri impossible : {r['message']}"}
        a = r["analyse"]
        p = parcours(a)
        note = f"Tri : {a['categorie']} - {a['motif']}"
        if a["manipulation"]:
            note += " ATTENTION : tentative de manipulation détectée dans l'email."
        trace.evenement("parcours", fil_id=etat["fil_id"], parcours=p)
        return maj | {"analyse": a, "parcours": p, "decision_agent": DECISION[p], "note": note}

    def apres_trier(etat: EtatPipeline) -> str:
        if etat.get("issue"):
            return END
        return {"transmettre": "transmettre", "proposer": "rechercher",
                "confirmer": "choisir_visite"}.get(etat["parcours"], "rediger")

    # ------------------------------------------------------- recherche --- #
    def rechercher(etat: EtatPipeline) -> dict:
        a = etat["analyse"]
        faits = rassembler(a, outils, agenda, maintenant(etat), trace)
        appels = max(1, len(a["besoin"]["references"])) + 1
        if faits["erreurs"]:
            # Après une erreur d'outil : vérification forcée de la brique, un seul nouvel essai.
            bloquees = [n for n in faits["erreurs"] if not verificateur.disponibles(n, forcer=True)]
            if not bloquees:
                faits = rassembler(a, outils, agenda, maintenant(etat), trace)
                appels *= 2
            if faits["erreurs"]:
                detail = "; ".join(f"{n} : {e.get('message')}" for n, e in faits["erreurs"].items())
                trace.evenement("incident", fil_id=etat["fil_id"], etape="recherche", detail=detail)
                return {"parcours": "transmettre", "decision_agent": "transmettre",
                        "faits": faits, "appels_outils": etat.get("appels_outils", 0) + appels,
                        "note": etat.get("note", "") + f" Brique en erreur : {detail}"}
        return {"faits": faits, "appels_outils": etat.get("appels_outils", 0) + appels}

    def apres_rechercher(etat: EtatPipeline) -> str:
        return "transmettre" if etat["parcours"] == "transmettre" else "rediger"

    # -------------------------------------------------------- rédaction --- #
    def rediger_email(etat: EtatPipeline) -> dict:
        a, p = etat["analyse"], etat["parcours"]
        base = {"nom_client": a["nom_client"]}
        creneaux: list[Creneau] = []
        maj: dict = {}
        if p == "proposer":
            f = etat["faits"]
            biens = f["biens"]
            faits = base | {"criteres": a["besoin"], "biens": biens,
                            "introuvables": f["introuvables"], "indisponibles": f["indisponibles"],
                            "periode": f["fenetre"], "ajustements": f["ajustements"]}
            creneaux = f["creneaux"] if biens else []
            maj = {"biens_proposes": biens, "creneaux_proposes": creneaux}
            cas = "proposer"
        elif p == "demander_precision":
            faits, cas = base | {"manquant": manquant(a)}, "demander_precision"
        else:  # repondre_agence
            fiche = fiche_agence(outils)
            if not fiche["ok"]:
                return {"parcours": "transmettre", "decision_agent": "transmettre",
                        "note": etat.get("note", "") + f" Fiche agence illisible : {fiche['message']}"}
            faits, cas = base | {"fiche_agence": fiche["texte"]}, "repondre_agence"
        r = rediger(client, cfg, trace, cas=cas, demande=etat["demande"], faits=faits,
                    creneaux=creneaux)
        maj |= _compter(etat, r)
        if not r["ok"]:
            return maj | {"parcours": "transmettre", "decision_agent": "transmettre",
                          "note": etat.get("note", "") + f" Rédaction impossible : {r['message']}"}
        note = " ".join(x for x in (etat.get("note", ""), r["note"]) if x)
        return maj | {"brouillon_texte": r["email"], "note": note}

    def apres_rediger(etat: EtatPipeline) -> str:
        return "transmettre" if etat["parcours"] == "transmettre" else "preparer"

    # --------------------------------------------- brouillon + validation --- #
    def preparer(etat: EtatPipeline) -> dict:
        if not verificateur.disponibles("gmail"):
            incident = rapport(verificateur.verifier("gmail"))
            trace.evenement("incident", fil_id=etat["fil_id"], etape="brouillon", detail=incident)
            return {"issue": "reporte", "incident": incident}
        brouillon = messagerie.creer_brouillon(etat["fil_id"], etat["brouillon_texte"])
        if not brouillon.get("ok"):
            trace.evenement("incident", fil_id=etat["fil_id"], etape="brouillon", detail=brouillon)
            return {"issue": "reporte", "incident": brouillon.get("message")}
        messagerie.changer_libelle(etat["message_id"], "en_attente_validation")
        proposition: Proposition = {
            "type": "envoyer_brouillon", "fil_id": etat["fil_id"],
            "arguments": {"brouillon_id": brouillon["brouillon_id"]},
            "texte": etat["brouillon_texte"], "note": etat.get("note", ""),
            "resume": f"Réponse à {etat['expediteur']} ({etat.get('decision_agent')})",
        }
        trace.evenement("validation_demandee", fil_id=etat["fil_id"], proposition=proposition)
        return {"proposition": proposition, "decision": None, "incident": None}

    def choisir_visite(etat: EtatPipeline) -> dict:
        a = etat["analyse"]
        proposes = etat.get("creneaux_proposes") or []
        n = a.get("numero_creneau")
        if not proposes or n is None or not 1 <= n <= len(proposes):
            return {"parcours": "transmettre", "decision_agent": "transmettre",
                    "note": etat.get("note", "") + " Créneau choisi non identifié parmi ceux proposés."}
        biens = etat.get("biens_proposes") or []
        cites = [b for b in biens if b["id"] in a["besoin"]["references"]]
        bien = cites[0] if len(cites) == 1 else (biens[0] if len(biens) == 1 else None)
        if bien is None:
            return {"parcours": "transmettre", "decision_agent": "transmettre",
                    "note": etat.get("note", "") + " Le client n'a pas précisé quel bien visiter."}
        creneau = proposes[n - 1]
        nom, adresse_email = parseaddr(etat["expediteur"])
        arguments = dict(conseiller=creneau["conseiller"], debut=creneau["debut"],
                         bien_id=bien["id"], adresse=bien["adresse"],
                         client_nom=a["nom_client"] or nom or adresse_email,
                         client_email=adresse_email, fil_id=etat["fil_id"])
        messagerie.changer_libelle(etat["message_id"], "en_attente_validation")
        proposition: Proposition = {
            "type": "creer_visite", "fil_id": etat["fil_id"], "arguments": arguments,
            "note": etat.get("note", ""),
            "resume": (f"Visite {bien['id']} ({bien['adresse']}) le {libelle_creneau(creneau['debut'])}"
                       f" avec {CONSEILLERS.get(creneau['conseiller'])} pour {arguments['client_nom']}"),
        }
        trace.evenement("validation_demandee", fil_id=etat["fil_id"], proposition=proposition)
        return {"proposition": proposition, "creneau_choisi": creneau, "decision": None,
                "incident": None}

    def apres_choisir(etat: EtatPipeline) -> str:
        return "transmettre" if etat["parcours"] == "transmettre" else "valider"

    def valider(etat: EtatPipeline) -> dict:
        decision = interrupt({"fil_id": etat["fil_id"], "proposition": etat["proposition"],
                              "incident": etat.get("incident")})
        probleme = controler(decision, etat["proposition"])
        trace.evenement("decision", fil_id=etat["fil_id"], decision=decision, probleme=probleme)
        return {"decision": None if probleme else decision, "incident": probleme}

    def apres_valider(etat: EtatPipeline) -> str:
        d = etat.get("decision")
        if d is None:
            return "valider"
        return "refuser" if d["action"] == "refuser" else "ecrire"

    def ecrire(etat: EtatPipeline) -> dict:
        proposition, decision = etat["proposition"], etat["decision"]
        brique = BRIQUE[proposition["type"]]
        if not verificateur.disponibles(brique, forcer=True):
            incident = rapport(verificateur.verifier(brique))
            trace.evenement("incident", fil_id=etat["fil_id"], etape="ecriture", detail=incident)
            return {"decision": None, "incident": f"Rien n'a été écrit. {incident}"}
        resultat = appliquer(proposition, decision, agenda, messagerie)
        trace.evenement("ecriture", fil_id=etat["fil_id"], type=proposition["type"],
                        conseiller=decision.get("conseiller"), resultat=resultat)
        if proposition["type"] == "creer_visite":
            if resultat.get("ok"):
                return {"visite": proposition["arguments"] | {"evenement_id": resultat["evenement_id"]},
                        "parcours": "confirmer_visite"}
            if resultat.get("code") == "CRENEAU_INDISPONIBLE":
                return {"parcours": "creneau_pris"}
        if not resultat.get("ok"):
            return {"decision": None, "incident": f"Échec de l'écriture : {resultat.get('message')}"}
        messagerie.changer_libelle(etat["message_id"], "repondu")
        return {"issue": "envoye"}

    def apres_ecrire(etat: EtatPipeline) -> str:
        if etat.get("issue"):
            return END
        if etat["parcours"] in ("confirmer_visite", "creneau_pris") and etat.get("decision"):
            return "suite_visite"
        return "valider"

    def suite_visite(etat: EtatPipeline) -> dict:
        """Après la décision sur la visite : email de confirmation, ou nouveaux créneaux."""
        a, creneau = etat["analyse"], etat["creneau_choisi"]
        if etat["parcours"] == "confirmer_visite":
            v = etat["visite"]
            faits = {"nom_client": a["nom_client"],
                     "visite": {"bien_id": v["bien_id"], "adresse": v["adresse"],
                                "conseiller": CONSEILLERS.get(v["conseiller"])}}
            r = rediger(client, cfg, trace, cas="confirmer_visite", demande=etat["demande"],
                        faits=faits, creneaux=[creneau])
            maj = {"creneaux_proposes": []}
        else:
            jour = JOURS[datetime.fromisoformat(creneau["debut"]).astimezone(DAKAR).weekday()]
            dispo = {"jour": jour, "semaine_prochaine": False, "plage": None, "heure": None}
            f = rassembler({"besoin": {"type": None, "quartier": None, "loyer_max": None,
                                       "pieces": None, "references": []},
                            "disponibilites": dispo}, outils, agenda, maintenant(etat), trace)
            nouveaux = [c for c in f["creneaux"] if c["debut"] != creneau["debut"]]
            r = rediger(client, cfg, trace, cas="creneau_pris", demande=etat["demande"],
                        faits={"nom_client": a["nom_client"], "periode": f["fenetre"]},
                        creneaux=nouveaux)
            maj = {"creneaux_proposes": nouveaux}
        maj |= _compter(etat, r) | {"decision": None}
        if not r["ok"]:
            return maj | {"parcours": "transmettre", "decision_agent": "transmettre",
                          "note": etat.get("note", "") + f" Rédaction impossible : {r['message']}"}
        return maj | {"brouillon_texte": r["email"],
                      "note": " ".join(x for x in (etat.get("note", ""), r["note"]) if x)}

    def apres_suite(etat: EtatPipeline) -> str:
        return "transmettre" if etat["parcours"] == "transmettre" else "preparer"

    # ------------------------------------------------------ sans écriture --- #
    def transmettre(etat: EtatPipeline) -> dict:
        messagerie.changer_libelle(etat["message_id"], "transmis")
        trace.evenement("transmis_conseiller", fil_id=etat["fil_id"], note=etat.get("note", ""))
        return {"issue": "transmis"}

    def refuser(etat: EtatPipeline) -> dict:
        messagerie.changer_libelle(etat["message_id"], "transmis")
        trace.evenement("refus_conseiller", fil_id=etat["fil_id"],
                        motif=(etat.get("decision") or {}).get("motif"))
        return {"issue": "refuse"}

    g = StateGraph(EtatPipeline)
    for nom, f in [("trier", trier), ("rechercher", rechercher), ("rediger", rediger_email),
                   ("preparer", preparer), ("choisir_visite", choisir_visite),
                   ("valider", valider), ("ecrire", ecrire), ("suite_visite", suite_visite),
                   ("transmettre", transmettre), ("refuser", refuser)]:
        g.add_node(nom, f)
    g.add_edge(START, "trier")
    g.add_conditional_edges("trier", apres_trier,
                            ["transmettre", "rechercher", "choisir_visite", "rediger", END])
    g.add_conditional_edges("rechercher", apres_rechercher, ["transmettre", "rediger"])
    g.add_conditional_edges("rediger", apres_rediger, ["transmettre", "preparer"])
    g.add_conditional_edges("preparer", lambda e: END if e.get("issue") else "valider",
                            ["valider", END])
    g.add_conditional_edges("choisir_visite", apres_choisir, ["transmettre", "valider"])
    g.add_conditional_edges("valider", apres_valider, ["valider", "ecrire", "refuser"])
    g.add_conditional_edges("ecrire", apres_ecrire, ["valider", "suite_visite", END])
    g.add_conditional_edges("suite_visite", apres_suite, ["transmettre", "preparer"])
    g.add_edge("transmettre", END)
    g.add_edge("refuser", END)
    return g.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------- #
# Pilotage                                                                    #
# --------------------------------------------------------------------------- #

RECURSION = 60


def traiter(graphe, demande: Demande) -> dict:
    """Traite un email jusqu'à la pause de validation ou la fin. Si le fil attend déjà
    une décision de conseiller, l'email est laissé « à traiter » (rien n'est écrasé)."""
    fil_id = demande["fil_id"]
    if graphe.get_state(config_fil(fil_id)).interrupts:
        return situation(graphe, fil_id) | {"issue": "reporte",
                                            "raison": "une validation est déjà en attente sur ce fil"}
    entree: EtatPipeline = {
        "demande": demande, "fil_id": fil_id, "message_id": demande["message_id"],
        "expediteur": demande["expediteur"],
        "analyse": None, "parcours": None, "decision_agent": None, "note": "", "faits": None,
        "brouillon_texte": None, "proposition": None, "decision": None, "incident": None,
        "issue": None, "tokens_entree": 0, "tokens_sortie": 0, "appels_modele": 0,
        "appels_outils": 0,
    }
    graphe.invoke(entree, config_fil(fil_id, RECURSION))
    return situation(graphe, fil_id)


def resultat_evaluation(s: dict) -> dict:
    """Ce que le script d'évaluation de Fatou compare au résultat attendu."""
    etat = s["etat"]
    texte = (s["en_attente"] or {}).get("proposition", {}).get("texte") or ""
    return {
        "decision": etat.get("decision_agent"),
        "reponse": texte,
        "creneaux": [c["debut"] for c in etat.get("creneaux_proposes") or []]
        if etat.get("decision_agent") == "repondre" and etat.get("biens_proposes") else None,
        "appels_outils": etat.get("appels_outils", 0),
        "tokens_entree": etat.get("tokens_entree", 0),
        "tokens_sortie": etat.get("tokens_sortie", 0),
    }
