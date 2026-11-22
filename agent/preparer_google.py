"""Vérifie (et prépare) le compte Google de test avant une démonstration réelle.

    python -m agent.preparer_google

N'envoie aucun email et ne crée aucun événement. Seule écriture : les libellés
SamaKer/… manquants sont créés dans Gmail (sans effet sur les messages).
Affiche « ok » ou ce qui manque, étape par étape ; code de sortie 0 si tout est prêt.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from agent.dates import DAKAR
from contracts import CONSEILLERS, LIBELLES


def verifier_configuration(env=os.environ) -> list[str]:
    """Ce qui manque dans .env et secrets/ (aucune connexion)."""
    problemes = []
    credentials = Path(env.get("GOOGLE_CREDENTIALS", "secrets/credentials.json"))
    if not credentials.is_file():
        problemes.append(f"fichier OAuth absent : {credentials} (à demander à Papa)")
    for c in CONSEILLERS:
        if not env.get(f"CALENDAR_ID_{c.upper()}", "").strip():
            problemes.append(f"CALENDAR_ID_{c.upper()} vide dans .env")
    if not env.get("AGENCE_EMAIL", "").strip():
        problemes.append("AGENCE_EMAIL vide dans .env")
    if env.get("BRIQUES", "factice").lower() != "google":
        problemes.append("BRIQUES n'est pas « google » dans .env (l'agent utiliserait les factices)")
    return problemes


def preparer_libelles(service_gmail) -> tuple[list[str], list[str]]:
    """(libellés créés, libellés déjà présents)."""
    labels = service_gmail.users().labels()
    existants = {l.get("name") for l in labels.list(userId="me").execute().get("labels", [])}
    crees, presents = [], []
    for nom in LIBELLES.values():
        if nom in existants:
            presents.append(nom)
        else:
            labels.create(userId="me", body={"name": nom}).execute()
            crees.append(nom)
    return crees, presents


def compte_gmail(service_gmail) -> str:
    return service_gmail.users().getProfile(userId="me").execute().get("emailAddress", "")


def verifier_agendas(agenda, maintenant: datetime) -> dict[str, dict]:
    """Par conseiller : créneaux libres sur 7 jours, ou erreur."""
    fin = maintenant + timedelta(days=7)
    return {c: agenda.lister_creneaux_libres(c, maintenant.isoformat(), fin.isoformat())
            for c in CONSEILLERS}


def main() -> None:
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    pret = True

    def ligne(ok: bool, texte: str) -> None:
        nonlocal pret
        pret &= ok
        print(f"  {'ok    ' if ok else 'ERREUR'}  {texte}")

    print("1. Configuration (.env et secrets/)")
    problemes = verifier_configuration()
    for p in problemes:
        ligne(False, p)
    if problemes:
        sys.exit("\nCompléter la configuration, puis relancer.")
    ligne(True, "fichier OAuth, agendas des conseillers, adresse de l'agence, BRIQUES=google")

    print("\n2. Connexion Google (la première fois : navigateur, se connecter avec le COMPTE DE L'AGENCE)")
    from integrations.google.calendar import AgendaGoogle
    from integrations.google.gmail import MessagerieGoogle
    messagerie, agenda = MessagerieGoogle.connecter(), AgendaGoogle.connecter()
    for nom, brique in (("Gmail", messagerie), ("Calendar", agenda)):
        if isinstance(brique, dict):
            ligne(False, f"{nom} : [{brique['code']}] {brique['message']}")
            sys.exit("\nConnexion impossible.")
    ligne(True, "Gmail et Calendar autorisés")

    print("\n3. Compte Gmail")
    adresse, attendue = compte_gmail(messagerie._service), os.environ["AGENCE_EMAIL"].strip()
    ligne(adresse.lower() == attendue.lower(),
          f"connecté en tant que {adresse}" + ("" if adresse.lower() == attendue.lower()
                                               else f" au lieu de AGENCE_EMAIL ({attendue})"))
    crees, presents = preparer_libelles(messagerie._service)
    for nom in presents:
        ligne(True, f"libellé {nom}")
    for nom in crees:
        ligne(True, f"libellé {nom} (créé)")
    etat = messagerie.verifier_etat()
    ligne(etat.get("ok", False), f"verifier_etat Gmail : {etat.get('message', 'ok')}")

    print("\n4. Agendas des conseillers (créneaux libres sur 7 jours)")
    for c, r in verifier_agendas(agenda, datetime.now(DAKAR)).items():
        ligne(r.get("ok", False), f"{CONSEILLERS[c]} : " + (
            f"{len(r['creneaux'])} créneaux libres" if r.get("ok") else f"[{r['code']}] {r['message']}"))
    etat = agenda.verifier_etat()
    ligne(etat.get("ok", False), f"verifier_etat Calendar : {etat.get('message', 'ok')}")

    print("\n" + ("Tout est prêt. Écrire à " + attendue + " depuis une autre adresse, puis :\n"
                  "  python -m agent.conseiller releve" if pret else "Au moins un point est à corriger."))
    sys.exit(0 if pret else 1)


if __name__ == "__main__":
    main()
