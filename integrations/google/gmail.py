"""Integration Google Gmail."""

from __future__ import annotations

import base64
from time import perf_counter
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from contracts import FUSEAU, LIBELLES, EtatMessage, Erreur, erreur
from integrations.google.auth import obtenir_identifiants


SCOPES_GMAIL = [
    "https://www.googleapis.com/auth/gmail.modify",
]


class _ExtracteurHTML(HTMLParser):
    """Convertit un contenu HTML en texte lisible."""

    BLOCS = {
        "br", "p", "div", "li", "tr",
        "h1", "h2", "h3", "h4", "hr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.BLOCS:
            self.fragments.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCS:
            self.fragments.append("\n")

    def handle_data(self, data: str) -> None:
        self.fragments.append(data)

    def texte(self) -> str:
        return " ".join(
            ligne.strip()
            for ligne in "".join(self.fragments).splitlines()
            if ligne.strip()
        )


def _decoder_entete(valeur: str) -> str:
    """Decode un en-tete MIME."""
    try:
        return str(make_header(decode_header(valeur)))
    except (TypeError, ValueError, LookupError):
        return valeur


def _decoder_partie(partie: dict[str, Any]) -> str:
    """Decode le contenu texte d'une partie MIME."""
    donnees = partie.get("body", {}).get("data")

    if not donnees:
        return ""

    contenu = base64.urlsafe_b64decode(
        donnees + "=" * (-len(donnees) % 4)
    )

    entete = Message()
    entete["Content-Type"] = partie.get("mimeType", "text/plain")
    charset = entete.get_content_charset() or "utf-8"

    return contenu.decode(charset, errors="replace")


def _extraire_textes(
    partie: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Recupere les contenus texte sans les pieces jointes."""
    if partie.get("filename"):
        return [], []

    textes: list[str] = []
    html: list[str] = []

    mime_type = partie.get("mimeType", "")

    if mime_type == "text/plain":
        texte = _decoder_partie(partie)
        if texte:
            textes.append(texte)

    elif mime_type == "text/html":
        contenu = _decoder_partie(partie)
        if contenu:
            html.append(contenu)

    for enfant in partie.get("parts", []):
        textes_enfant, html_enfant = _extraire_textes(enfant)
        textes.extend(textes_enfant)
        html.extend(html_enfant)

    return textes, html


def _extraire_corps(payload: dict[str, Any]) -> str:
    """Extrait le texte brut du message."""
    textes, contenus_html = _extraire_textes(payload)

    if textes:
        return "\n".join(textes).strip()

    if contenus_html:
        extracteur = _ExtracteurHTML()
        extracteur.feed("\n".join(contenus_html))
        return extracteur.texte()

    return ""


def _date_reception(message: dict[str, Any]) -> str:
    """Convertit la date Gmail en ISO 8601, fuseau de Dakar."""
    date_ms = message.get("internalDate")

    if date_ms is None:
        raise ValueError("Date de reception Gmail absente.")

    date_utc = datetime.fromtimestamp(
        int(date_ms) / 1000,
        tz=timezone.utc,
    )

    return date_utc.astimezone(ZoneInfo(FUSEAU)).isoformat()


def _erreur_api(exc: Exception) -> Erreur:
    """Convertit une erreur technique en erreur du contrat."""
    statut = getattr(getattr(exc, "resp", None), "status", None)

    if statut == 404:
        return erreur(
            "INTROUVABLE",
            "Le brouillon Gmail est introuvable.",
        )

    if statut in (401, 403):
        return erreur(
            "AUTORISATION",
            "Acces Google Gmail refuse. Verifiez les autorisations OAuth.",
        )

    if statut in (408, 504):
        return erreur(
            "DELAI_DEPASSE",
            "Le delai de reponse de Google Gmail est depasse.",
        )

    if statut == 429 or (isinstance(statut, int) and statut >= 500):
        return erreur(
            "INDISPONIBLE",
            "Le service Google Gmail est temporairement indisponible.",
        )

    return erreur(
        "INTERNE",
        f"Erreur pendant une operation Gmail ({type(exc).__name__}).",
    )


class MessagerieGoogle:
    """Client Google Gmail conforme au contrat Messagerie."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def connecter(cls) -> MessagerieGoogle | Erreur:
        """Authentifie Google et initialise le service Gmail."""
        identifiants = obtenir_identifiants(SCOPES_GMAIL)

        if isinstance(identifiants, dict):
            return identifiants

        try:
            service = build(
                "gmail",
                "v1",
                credentials=identifiants,
                cache_discovery=False,
            )
        except Exception as exc:
            return erreur(
                "INDISPONIBLE",
                f"Initialisation de Google Gmail impossible ({type(exc).__name__}).",
            )

        return cls(service)

    def lire_demandes(self) -> dict[str, Any] | Erreur:
        """Lit les messages portant le libelle a traiter."""
        try:
            reponse_libelles = (
                self._service.users()
                .labels()
                .list(userId="me")
                .execute()
            )

            nom_libelle = LIBELLES["a_traiter"]
            libelle = next(
                (
                    element
                    for element in reponse_libelles.get("labels", [])
                    if element.get("name") == nom_libelle
                ),
                None,
            )

            if libelle is None:
                return {"ok": True, "demandes": []}

            libelle_id = libelle["id"]
            demandes = []
            page_token = None

            while True:
                arguments = {
                    "userId": "me",
                    "labelIds": [libelle_id],
                    "maxResults": 100,
                }

                if page_token:
                    arguments["pageToken"] = page_token

                reponse = (
                    self._service.users()
                    .messages()
                    .list(**arguments)
                    .execute()
                )

                for element in reponse.get("messages", []):
                    message = (
                        self._service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=element["id"],
                            format="full",
                        )
                        .execute()
                    )

                    entetes = {
                        entete["name"].lower(): entete["value"]
                        for entete in message.get("payload", {}).get(
                            "headers", []
                        )
                    }

                    demandes.append({
                        "message_id": message["id"],
                        "fil_id": message["threadId"],
                        "expediteur": _decoder_entete(
                            entetes.get("from", "")
                        ),
                        "sujet": _decoder_entete(
                            entetes.get("subject", "")
                        ),
                        "corps": _extraire_corps(
                            message.get("payload", {})
                        ),
                        "recu_le": _date_reception(message),
                    })

                page_token = reponse.get("nextPageToken")

                if not page_token:
                    break

            return {"ok": True, "demandes": demandes}

        except Exception as exc:
            return _erreur_api(exc)

    def creer_brouillon(
        self,
        fil_id: str,
        texte: str,
    ) -> dict[str, Any] | Erreur:
        """Cree un brouillon de reponse dans le fil d'origine."""
        if (
            not isinstance(fil_id, str)
            or not fil_id.strip()
            or not isinstance(texte, str)
            or not texte.strip()
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "Le fil et le texte de reponse sont obligatoires.",
            )

        try:
            fil = (
                self._service.users()
                .threads()
                .get(
                    userId="me",
                    id=fil_id,
                    format="full",
                )
                .execute()
            )

            messages = fil.get("messages", [])

            if not messages:
                return erreur(
                    "INTROUVABLE",
                    "Aucun message trouve dans ce fil Gmail.",
                )

            messages_admissibles = [
                message
                for message in messages
                if not {"DRAFT", "SENT"}.intersection(
                    message.get("labelIds", [])
                )
            ]

            if not messages_admissibles:
                return erreur(
                    "INTROUVABLE",
                    "Aucun message recu trouve dans ce fil Gmail.",
                )

            dernier_message = messages_admissibles[-1]
            entetes = {
                entete["name"].lower(): entete["value"]
                for entete in dernier_message.get(
                    "payload", {}
                ).get("headers", [])
            }

            expediteur = entetes.get("from", "").strip()
            sujet = entetes.get("subject", "").strip()

            if not expediteur:
                return erreur(
                    "INTROUVABLE",
                    "L'expediteur du dernier message est introuvable.",
                )

            message = EmailMessage()
            message["To"] = expediteur

            if sujet.lower().startswith("re:"):
                message["Subject"] = sujet
            else:
                message["Subject"] = f"Re: {sujet}" if sujet else "Re: (sans sujet)"

            message_id = entetes.get("message-id", "").strip()
            references = entetes.get("references", "").strip()

            if message_id:
                message["In-Reply-To"] = message_id

            if references and message_id:
                message["References"] = f"{references} {message_id}"
            elif references:
                message["References"] = references
            elif message_id:
                message["References"] = message_id

            message.set_content(texte.strip())

            contenu_encode = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("ascii").rstrip("=")

            brouillon = (
                self._service.users()
                .drafts()
                .create(
                    userId="me",
                    body={
                        "message": {
                            "threadId": fil_id,
                            "raw": contenu_encode,
                        }
                    },
                )
                .execute()
            )

            return {
                "ok": True,
                "brouillon_id": brouillon["id"],
            }

        except Exception as exc:
            return _erreur_api(exc)

    def envoyer_brouillon(
        self,
        brouillon_id: str,
    ) -> dict[str, Any] | Erreur:
        """Envoie un brouillon apres validation humaine."""
        if not isinstance(brouillon_id, str) or not brouillon_id.strip():
            return erreur(
                "ARGUMENT_INVALIDE",
                "L'identifiant du brouillon est obligatoire.",
            )

        try:
            (
                self._service.users()
                .drafts()
                .send(
                    userId="me",
                    body={"id": brouillon_id.strip()},
                )
                .execute()
            )

            return {"ok": True}

        except Exception as exc:
            return _erreur_api(exc)

    def changer_libelle(
        self,
        message_id: str,
        etat: EtatMessage,
    ) -> dict[str, Any] | Erreur:
        """Remplace le libelle d'etat SamaKer d'un message."""
        if (
            not isinstance(message_id, str)
            or not message_id.strip()
            or not isinstance(etat, str)
            or etat not in LIBELLES
        ):
            return erreur(
                "ARGUMENT_INVALIDE",
                "L'identifiant du message ou son etat est invalide.",
            )

        try:
            service_labels = self._service.users().labels()

            reponse = (
                service_labels
                .list(userId="me")
                .execute()
            )

            libelles_etat = {
                element["name"]: element["id"]
                for element in reponse.get("labels", [])
                if element.get("name") in LIBELLES.values()
                and element.get("id")
            }

            nom_cible = LIBELLES[etat]
            identifiant_cible = libelles_etat.get(nom_cible)

            if not identifiant_cible:
                nouveau_libelle = (
                    service_labels
                    .create(
                        userId="me",
                        body={"name": nom_cible},
                    )
                    .execute()
                )
                identifiant_cible = nouveau_libelle.get("id")

                if not identifiant_cible:
                    return erreur(
                        "INTERNE",
                        "Impossible de recuperer le nouvel identifiant de libelle.",
                    )

            identifiants_a_retirer = [
                identifiant
                for nom, identifiant in libelles_etat.items()
                if nom != nom_cible
            ]

            (
                self._service.users()
                .messages()
                .modify(
                    userId="me",
                    id=message_id.strip(),
                    body={
                        "addLabelIds": [identifiant_cible],
                        "removeLabelIds": identifiants_a_retirer,
                    },
                )
                .execute()
            )

            return {"ok": True}

        except Exception as exc:
            return _erreur_api(exc)


    def verifier_etat(self) -> dict[str, Any] | Erreur:
        """Verifie l'acces a Gmail et la presence des quatre libelles."""
        debut = perf_counter()

        try:
            utilisateurs = self._service.users()

            utilisateurs.getProfile(userId="me").execute()

            resultat_libelles = (
                utilisateurs.labels()
                .list(userId="me")
                .execute()
            )

            noms_libelles = {
                libelle.get("name")
                for libelle in resultat_libelles.get("labels", [])
            }

            libelles_manquants = [
                nom
                for nom in LIBELLES.values()
                if nom not in noms_libelles
            ]

            if libelles_manquants:
                return erreur(
                    "INTROUVABLE",
                    "Libelles Gmail manquants : "
                    + ", ".join(libelles_manquants)
                    + ".",
                )

            latence_ms = int((perf_counter() - debut) * 1000)

            return {
                "ok": True,
                "latence_ms": latence_ms,
            }

        except Exception as exc:
            return _erreur_api(exc)
