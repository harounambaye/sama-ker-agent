import time

import pytest

from agent.etat import VerificateurEtat, bloquer_si_indisponible


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def compteur():
    n = {"appels": 0}

    def sonde():
        n["appels"] += 1
        return {"ok": True}

    return sonde, n


def test_resultat_conserve_une_minute():
    sonde, n = compteur()
    h = Horloge()
    v = VerificateurEtat({"a": sonde}, ttl_s=60, horloge=h)
    v.verifier()
    h.t = 59
    v.verifier()
    assert n["appels"] == 1
    h.t = 61
    v.verifier()
    assert n["appels"] == 2


def test_forcer_ignore_le_cache():
    sonde, n = compteur()
    v = VerificateurEtat({"a": sonde})
    v.verifier()
    v.verifier(forcer=True)
    assert n["appels"] == 2


def test_latence_ajoutee_si_absente():
    sonde, _ = compteur()
    assert "latence_ms" in VerificateurEtat({"a": sonde}).verifier()["a"]


def test_exception_convertie_en_erreur():
    def panne():
        raise ConnectionError("refusée")

    r = VerificateurEtat({"b": panne}).verifier()["b"]
    assert r == {"ok": False, "code": "INDISPONIBLE", "message": "b : ConnectionError: refusée"}


def test_reponse_non_conforme():
    r = VerificateurEtat({"d": lambda: "oui"}).verifier()["d"]
    assert r["code"] == "INTERNE"


def test_delai_depasse_sans_bloquer_les_autres():
    sonde, _ = compteur()
    v = VerificateurEtat({"lente": lambda: time.sleep(2), "a": sonde}, delai_s=0.3)
    t0 = time.perf_counter()
    r = v.verifier()
    assert time.perf_counter() - t0 < 1.5
    assert r["lente"]["code"] == "DELAI_DEPASSE"
    assert r["a"]["ok"]


def test_brique_inconnue():
    with pytest.raises(KeyError):
        VerificateurEtat({}).verifier("absente")


def test_demarrage_bloque_si_une_brique_est_en_erreur(capsys):
    v = VerificateurEtat({"ok": lambda: {"ok": True}, "ko": lambda: 1 / 0})
    with pytest.raises(SystemExit) as fin:
        bloquer_si_indisponible(v)
    assert fin.value.code == 2
    assert "ko" in capsys.readouterr().err


def test_demarrage_autorise_si_tout_va_bien():
    bloquer_si_indisponible(VerificateurEtat({"ok": lambda: {"ok": True}}))
