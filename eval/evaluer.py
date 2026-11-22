"""Évaluation de l'agent Sama Kër Immobilier sur le jeu de 15 emails (exercice 6).

Lancement, depuis la racine du dépôt :
    python -m eval.evaluer --etiquette apres              # pipeline complet (clé API nécessaire)
    python -m eval.evaluer --etiquette avant --agent validation  # graphe de validation
    python -m eval.evaluer --etiquette ex1 --agent exercice1  # boucle de l'exercice 1
    python -m eval.evaluer --etiquette essai --simulation # sans API : teste le script lui-même
    python -m eval.evaluer --etiquette avant --limite 3   # seulement les 3 premiers emails

Pour chaque email, le script fait traiter le message par l'agent, compare le résultat
avec eval/emails_test.json et mesure : réussite, appels d'outils, tokens et temps.
Résultats : eval/resultats/<etiquette>.json (détail) et eval/resultats/<etiquette>.md (tableau).
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
FICHIER_EMAILS = DOSSIER / "emails_test.json"
DOSSIER_RESULTATS = DOSSIER / "resultats"

REFERENCE_BIEN = re.compile(r"SK-\d{3}")
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5}


# --------------------------------------------------------------------------- #
# 1. Faire traiter un email par l'agent                                       #
# --------------------------------------------------------------------------- #
# Chaque adaptateur renvoie un dictionnaire de la même forme :
#   decision          "repondre", "demander_precision", "transmettre", "creer_visite" ou None
#   reponse           texte du brouillon rédigé par l'agent ("" si aucun)
#   creneaux          liste de débuts de créneaux proposés, ISO 8601 (None si non fourni)
#   appels_outils, tokens_entree, tokens_sortie
# adaptateur_pipeline (pipeline complet) est utilisé par défaut.


def texte_de_l_email(email: dict) -> str:
    """Le message tel que l'agent le reçoit : expéditeur, objet et corps."""
    return f"De : {email['expediteur']}\nObjet : {email['objet']}\n\n{email['corps']}"


def adaptateur_agent():
    """Agent actuel (boucle de l'exercice 1) branché sur le catalogue."""
    from agent import config
    from agent.graphe import construire_graphe, executer
    from agent.outils import OutilsCatalogueLocal
    from agent.traces import Trace

    try:
        from mcp_server.catalogue import CatalogueSQLite as Catalogue
    except ImportError:  # catalogue réel pas encore fusionné dans cette branche
        from agent.catalogue_factice import CatalogueFactice as Catalogue

    cfg = config.charger()

    def traiter(email: dict) -> dict:
        trace = Trace(cfg.traces_dir, etiquette=f"eval-{email['id']}", verbeux=False)
        graphe = construire_graphe(cfg, OutilsCatalogueLocal(Catalogue()), trace)
        etat = executer(graphe, cfg, texte_de_l_email(email), trace)
        return {
            "decision": None,  # pas encore produit par l'agent de l'exercice 1
            "reponse": etat.get("reponse", ""),
            "creneaux": None,  # pas encore produit par l'agent de l'exercice 1
            "appels_outils": etat.get("appels_outils", 0),
            "tokens_entree": etat.get("tokens_entree", 0),
            "tokens_sortie": etat.get("tokens_sortie", 0),
        }

    return traiter


def occuper_mardi_10h(agenda, maintenant=None):
    """Préparation de E07 : le créneau de mardi prochain 10 h 00 - 10 h 45 est déjà pris
    chez les trois conseillers. Les deux prochains mardis sont occupés, car « mardi
    prochain » peut désigner l'un ou l'autre selon le jour où l'évaluation est lancée."""
    from agent.dates import DAKAR
    from contracts import CONSEILLERS

    maintenant = maintenant or datetime.now(DAKAR)
    jours = (1 - maintenant.weekday()) % 7 or 7          # 1 = mardi
    mardi = (maintenant + timedelta(days=jours)).replace(hour=10, minute=0, second=0, microsecond=0)
    for jour in (mardi, mardi + timedelta(days=7)):
        for conseiller in CONSEILLERS:
            r = agenda.creer_visite(conseiller, jour.isoformat(), "SK-002", "Préparation E07",
                                    "Rendez-vous existant", "occupe@example.com",
                                    f"preparation-e07-{conseiller}-{jour:%Y%m%d}")
            if not r.get("ok"):
                raise RuntimeError(f"Préparation de E07 impossible : {r}")


def adaptateur_pipeline():
    """Pipeline complet de l'exercice 5 (tri, recherche, rédaction, validation).

    Chaque email est reçu dans une messagerie factice et traité jusqu'à la pause de
    validation : rien n'est envoyé. agent.pipeline.resultat_evaluation renvoie directement
    la décision (repondre, demander_precision, transmettre, creer_visite), la réponse,
    les créneaux proposés (ISO 8601), les appels d'outils et les tokens.
    """
    import tempfile

    from agent import config
    from agent.briques import sondes
    from agent.etat import VerificateurEtat
    from agent.factices import AgendaFactice, MessagerieFactice
    from agent.memoire import ouvrir_checkpointer
    from agent.outils import OutilsCatalogueLocal
    from agent.pipeline import construire_pipeline, resultat_evaluation
    from agent.pipeline import traiter as traiter_email
    from agent.traces import Trace
    from mcp_server.catalogue import CatalogueSQLite

    cfg = config.charger()
    catalogue = CatalogueSQLite()
    messagerie = MessagerieFactice()  # en mémoire : aucun vrai email
    agenda = AgendaFactice()          # en mémoire : aucun vrai agenda
    verificateur = VerificateurEtat(sondes(cfg, catalogue, agenda, messagerie))
    dossier = Path(tempfile.mkdtemp(prefix="eval-"))
    checkpointer = ouvrir_checkpointer(dossier / "checkpoints.sqlite")

    def traiter(email: dict) -> dict:
        if email.get("preparation"):      # E07 : créneau déjà pris
            occuper_mardi_10h(agenda)
        trace = Trace(cfg.traces_dir, etiquette=f"eval-{email['id']}", verbeux=False)
        graphe = construire_pipeline(
            cfg, OutilsCatalogueLocal(catalogue), agenda, messagerie, verificateur,
            trace, checkpointer,
        )
        demande = messagerie.recevoir(email["expediteur"], email["objet"], email["corps"])
        situation = traiter_email(graphe, demande)
        resultat = resultat_evaluation(situation)
        if situation.get("issue") == "reporte":
            resultat["decision"] = "reporte"
        return resultat

    return traiter


def adaptateur_graphe_validation():
    """Graphe de validation (intermédiaire, avant le pipeline complet) : chaque email est
    traité jusqu'à la pause de validation, puis laissé en attente. Rien n'est envoyé.
    Conservé pour pouvoir reproduire la colonne « avant » de la comparaison.

    Décisions renvoyées :
      "brouillon"   un brouillon de réponse attend la validation d'un conseiller
                    (couvre repondre, demander_precision et creer_visite) ;
      "transmettre" l'email est transmis à un conseiller, sans brouillon ;
      "reporte"     une brique était indisponible, rien n'a été écrit.
    """
    import tempfile

    from agent import config
    from agent.briques import sondes
    from agent.conversation import construire_graphe_conversation, demarrer
    from agent.etat import VerificateurEtat
    from agent.factices import AgendaFactice, MessagerieFactice
    from agent.memoire import ouvrir_checkpointer
    from agent.outils import OutilsCatalogueLocal
    from agent.traces import Trace

    try:
        from mcp_server.catalogue import CatalogueSQLite as Catalogue
    except ImportError:
        from agent.catalogue_factice import CatalogueFactice as Catalogue

    cfg = config.charger()
    catalogue = Catalogue()
    messagerie = MessagerieFactice()  # en mémoire : aucun vrai email
    agenda = AgendaFactice()
    verificateur = VerificateurEtat(sondes(cfg, catalogue, agenda, messagerie))
    dossier = Path(tempfile.mkdtemp(prefix="eval-"))
    checkpointer = ouvrir_checkpointer(dossier / "checkpoints.sqlite")

    def traiter(email: dict) -> dict:
        trace = Trace(cfg.traces_dir, etiquette=f"eval-{email['id']}", verbeux=False)
        graphe = construire_graphe_conversation(
            cfg, OutilsCatalogueLocal(catalogue), agenda, messagerie, verificateur,
            trace, checkpointer,
        )
        demande = messagerie.recevoir(email["expediteur"], email["objet"], email["corps"])
        situation = demarrer(graphe, cfg, demande)
        etat = situation["etat"]
        if situation["en_attente"]:
            decision = "brouillon"
            reponse = situation["en_attente"]["proposition"].get("texte", "")
        elif situation["issue"] == "transmis":
            decision, reponse = "transmettre", ""
        else:
            decision, reponse = "reporte", ""
        return {
            "decision": decision,
            "reponse": reponse,
            "creneaux": None,  # le pipeline ne renvoie pas de liste de créneaux
            "appels_outils": etat.get("appels_outils", 0),
            "tokens_entree": etat.get("tokens_entree", 0),
            "tokens_sortie": etat.get("tokens_sortie", 0),
        }

    return traiter


def adaptateur_simulation():
    """Faux agent qui renvoie exactement le résultat attendu, sans appeler l'API.
    Sert uniquement à vérifier que le script fonctionne : il doit obtenir 100 %."""

    def traiter(email: dict) -> dict:
        attendu = email["attendu"]
        mots = " ".join(attendu.get("doit_contenir", []))
        reponse = f"Biens proposés : {' '.join(attendu['biens_attendus'])}. {mots}".strip()
        creneaux = None
        if attendu.get("creneaux") and attendu["creneaux"]["jour"] in JOURS:
            c = attendu["creneaux"]
            jour = 9 + JOURS[c["jour"]]  # le 9 novembre 2026 est un lundi
            heures = [h for h in range(int(c["debut"][:2]), int(c["fin"][:2]))
                      if f"{h:02d}:00" != c.get("exclure")]
            creneaux = [f"2026-11-{jour:02d}T{h:02d}:00:00+00:00" for h in heures[: c["nombre"]]]
        return {
            "decision": attendu["decision"],
            "reponse": reponse,
            "creneaux": creneaux,
            "appels_outils": 1,
            "tokens_entree": 0,
            "tokens_sortie": 0,
        }

    return traiter


# --------------------------------------------------------------------------- #
# 2. Comparer le résultat avec l'attendu                                      #
# --------------------------------------------------------------------------- #


def sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


def verifier(attendu: dict, resultat: dict) -> list[str]:
    """Renvoie la liste des problèmes ; une liste vide veut dire « réussi »."""
    problemes = []
    reponse = resultat["reponse"]
    cites = set(REFERENCE_BIEN.findall(reponse))

    decision = resultat["decision"]
    if decision == "brouillon":
        # Graphe de validation (intermédiaire) : il ne distingue pas « répondre »
        # de « demander une précision » :
        # un brouillon est correct dès qu'une réponse rédigée était attendue.
        if attendu["decision"] == "transmettre":
            problemes.append("brouillon rédigé au lieu de transmettre à un conseiller")
    elif decision == "reporte":
        problemes.append("traitement reporté : une brique était indisponible")
    elif decision is not None and decision != attendu["decision"]:
        problemes.append(f"décision {decision} au lieu de {attendu['decision']}")

    if manquants := set(attendu["biens_attendus"]) - cites:
        problemes.append(f"biens attendus absents : {sorted(manquants)}")
    if interdits := set(attendu["biens_interdits"]) & cites:
        problemes.append(f"biens interdits proposés : {sorted(interdits)}")
    if attendu["decision"] in ("transmettre", "demander_precision") and cites:
        problemes.append(f"biens proposés alors qu'il fallait {attendu['decision']} : {sorted(cites)}")

    for mot in attendu.get("doit_contenir", []):
        if sans_accents(mot) not in sans_accents(reponse):
            problemes.append(f"la réponse ne contient pas « {mot} »")

    creneaux_attendus = attendu.get("creneaux")
    if creneaux_attendus and resultat["creneaux"] is not None:
        problemes += verifier_creneaux(creneaux_attendus, resultat["creneaux"])
    return problemes


def verifier_creneaux(attendu: dict, creneaux: list[str]) -> list[str]:
    problemes = []
    if len(creneaux) != attendu["nombre"]:
        problemes.append(f"{len(creneaux)} créneaux proposés au lieu de {attendu['nombre']}")
    for debut in creneaux:
        moment = datetime.fromisoformat(debut)
        heure = moment.strftime("%H:%M")
        if attendu["jour"] in JOURS and moment.weekday() != JOURS[attendu["jour"]]:
            problemes.append(f"créneau {debut} : pas un {attendu['jour']}")
        if not attendu["debut"] <= heure < attendu["fin"]:
            problemes.append(f"créneau {debut} : hors de la plage {attendu['debut']}-{attendu['fin']}")
        if attendu.get("exclure") == heure:
            problemes.append(f"créneau {debut} : c'est le créneau déjà pris")
    return problemes


# --------------------------------------------------------------------------- #
# 3. Rejouer le jeu de test et écrire les résultats                           #
# --------------------------------------------------------------------------- #


def evaluer(traiter, emails: list[dict]) -> list[dict]:
    lignes = []
    for email in emails:
        debut = time.perf_counter()
        try:
            resultat = traiter(email)
            problemes = verifier(email["attendu"], resultat)
        except Exception as exc:  # une panne sur un email ne doit pas arrêter l'évaluation
            resultat = {"decision": None, "reponse": "", "creneaux": None,
                        "appels_outils": 0, "tokens_entree": 0, "tokens_sortie": 0}
            problemes = [f"erreur pendant le traitement : {type(exc).__name__}: {exc}"]
        duree = time.perf_counter() - debut
        lignes.append({
            "id": email["id"],
            "categorie": email["categorie"],
            "reussi": not problemes,
            "problemes": problemes,
            "decision": resultat["decision"],
            "appels_outils": resultat["appels_outils"],
            "tokens": resultat["tokens_entree"] + resultat["tokens_sortie"],
            "duree_s": round(duree, 2),
            "reponse": resultat["reponse"],
        })
        print(f"{'OK' if not problemes else 'KO'}  {email['id']}  {email['categorie']}")
        for pb in problemes:
            print(f"      ! {pb}")
    return lignes


def resume(lignes: list[dict]) -> dict:
    n = len(lignes)
    return {
        "emails": n,
        "reussis": sum(l["reussi"] for l in lignes),
        "taux_reussite": round(100 * sum(l["reussi"] for l in lignes) / n, 1) if n else 0.0,
        "appels_outils_moyen": round(sum(l["appels_outils"] for l in lignes) / n, 1) if n else 0.0,
        "tokens_moyen": round(sum(l["tokens"] for l in lignes) / n) if n else 0,
        "duree_moyenne_s": round(sum(l["duree_s"] for l in lignes) / n, 2) if n else 0.0,
    }


def tableau_markdown(etiquette: str, lignes: list[dict], bilan: dict) -> str:
    texte = [
        f"# Évaluation « {etiquette} »",
        "",
        f"Taux de réussite : **{bilan['taux_reussite']} %** ({bilan['reussis']}/{bilan['emails']}) · "
        f"appels d'outils moyens : {bilan['appels_outils_moyen']} · "
        f"tokens moyens : {bilan['tokens_moyen']} · temps moyen : {bilan['duree_moyenne_s']} s",
        "",
        "| Email | Catégorie | Résultat | Appels d'outils | Tokens | Temps (s) | Problèmes |",
        "|---|---|---|---|---|---|---|",
    ]
    for l in lignes:
        texte.append(
            f"| {l['id']} | {l['categorie']} | {'OK' if l['reussi'] else 'KO'} | "
            f"{l['appels_outils']} | {l['tokens']} | {l['duree_s']} | {'; '.join(l['problemes']) or '-'} |"
        )
    return "\n".join(texte) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue l'agent sur le jeu de 15 emails.")
    parser.add_argument("--etiquette", required=True, help="nom de l'évaluation, ex. avant ou apres")
    parser.add_argument("--simulation", action="store_true", help="faux agent, sans appel à l'API")
    parser.add_argument("--agent", choices=["pipeline", "validation", "exercice1"],
                        default="pipeline",
                        help="pipeline complet (par défaut), graphe de validation "
                             "(intermédiaire) ou boucle de l'exercice 1")
    parser.add_argument("--limite", type=int, help="n'évaluer que les N premiers emails")
    args = parser.parse_args()

    emails = json.loads(FICHIER_EMAILS.read_text(encoding="utf-8"))["emails"]
    if args.limite:
        emails = emails[: args.limite]

    if args.simulation:
        traiter = adaptateur_simulation()
    elif args.agent == "exercice1":
        traiter = adaptateur_agent()
    elif args.agent == "validation":
        traiter = adaptateur_graphe_validation()
    else:
        traiter = adaptateur_pipeline()
    lignes = evaluer(traiter, emails)
    bilan = resume(lignes)

    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    (DOSSIER_RESULTATS / f"{args.etiquette}.json").write_text(
        json.dumps({"etiquette": args.etiquette, "bilan": bilan, "emails": lignes},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOSSIER_RESULTATS / f"{args.etiquette}.md").write_text(
        tableau_markdown(args.etiquette, lignes, bilan), encoding="utf-8"
    )
    print(f"\nTaux de réussite : {bilan['taux_reussite']} % ({bilan['reussis']}/{bilan['emails']})")
    print(f"Résultats écrits dans {DOSSIER_RESULTATS / args.etiquette}.json et .md")


if __name__ == "__main__":
    main()