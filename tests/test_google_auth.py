"""Tests de l'authentification Google."""

from integrations.google import auth


class FauxIdentifiants:
    """Simule des identifiants OAuth."""

    def __init__(self, valid=True, expired=False, refresh_token=None, scopes=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes or []

    def has_scopes(self, scopes):
        return set(scopes).issubset(set(self.scopes))

    def refresh(self, request):
        self.valid = True
        self.expired = False

    def to_json(self):
        return '{"token": "test"}'


def configurer_fichiers(tmp_path, monkeypatch):
    """Prépare des fichiers OAuth temporaires."""
    credentials = tmp_path / "credentials.json"
    token = tmp_path / "token.json"

    credentials.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("GOOGLE_CREDENTIALS", str(credentials))
    monkeypatch.setenv("GOOGLE_TOKEN", str(token))

    return credentials, token


def test_refuser_scopes_vides():
    resultat = auth.obtenir_identifiants([])

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_signaler_credentials_absents(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_CREDENTIALS",
        str(tmp_path / "absent.json"),
    )

    resultat = auth.obtenir_identifiants(
        ["https://www.googleapis.com/auth/calendar"]
    )

    assert resultat["ok"] is False
    assert resultat["code"] == "ARGUMENT_INVALIDE"


def test_reutiliser_identifiants_valides(tmp_path, monkeypatch):
    _, token = configurer_fichiers(tmp_path, monkeypatch)
    token.write_text("{}", encoding="utf-8")

    scopes = ["https://www.googleapis.com/auth/calendar"]
    identifiants = FauxIdentifiants(scopes=scopes)

    monkeypatch.setattr(
        auth.Credentials,
        "from_authorized_user_file",
        lambda chemin: identifiants,
    )

    resultat = auth.obtenir_identifiants(scopes)

    assert resultat is identifiants


def test_renouveler_identifiants_expires(tmp_path, monkeypatch):
    _, token = configurer_fichiers(tmp_path, monkeypatch)
    token.write_text("{}", encoding="utf-8")

    scopes = ["https://www.googleapis.com/auth/calendar"]
    identifiants = FauxIdentifiants(
        valid=False,
        expired=True,
        refresh_token="faux_refresh_token",
        scopes=scopes,
    )

    monkeypatch.setattr(
        auth.Credentials,
        "from_authorized_user_file",
        lambda chemin: identifiants,
    )

    resultat = auth.obtenir_identifiants(scopes)

    assert resultat is identifiants
    assert identifiants.valid is True
    assert token.read_text(encoding="utf-8") == '{"token": "test"}'
