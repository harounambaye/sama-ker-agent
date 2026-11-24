"""Poste du conseiller (Streamlit) piloté comme un utilisateur : email reçu, parcours
affiché, validation, écriture. Faux modèle, briques factices, aucun réseau."""

import json

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from agent.redaction import REPERE
from tests.test_pipeline import F3_MERMOZ, Client, email, json_modele, tri


@pytest.fixture
def poste(monkeypatch, tmp_path):
    for nom, valeur in {"BRIQUES": "factice", "CATALOGUE": "factice", "MODEL": "modele-de-test",
                        "FACTICES_DIR": str(tmp_path / "factices"),
                        "TRACES_DIR": str(tmp_path / "traces"),
                        "CHECKPOINT_DB": str(tmp_path / "cp.sqlite"),
                        "LANGSMITH_TRACING": "false"}.items():
        monkeypatch.setenv(nom, valeur)
    monkeypatch.setattr("agent.briques.sonde_modele",
                        lambda cfg, client=None: lambda: {"ok": True, "latence_ms": 0})
    client = Client([json_modele(tri(**F3_MERMOZ)), email(f"Nous avons le SK-001.\n\n{REPERE}")])
    monkeypatch.setattr("agent.pipeline.client_par_defaut", lambda: client)
    st.cache_resource.clear()
    at = AppTest.from_file("../poste_conseiller.py", default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    yield at, tmp_path
    st.cache_resource.clear()


def bouton(at, debut):
    return next(b for b in at.button if b.label.startswith(debut))


def test_email_recu_affiche_puis_valide_et_envoye(poste):
    at, dossier = poste
    assert "Aucune demande" in at.info[0].value
    bouton(at, "Recevoir et traiter").click().run()
    assert not at.exception, at.exception

    (fil,) = at.radio[0].options
    assert fil.startswith("⏸ Awa Ndiaye")
    (brouillon,) = [t for t in at.text_area if t.label.startswith("Email qui sera envoyé")]
    texte = brouillon.value
    assert texte.count("samedi") == 3 and REPERE not in texte
    assert any("⏸ À valider" in h.value for h in at.subheader)

    bouton(at, "✅ Approuver et envoyer").click().run()
    assert not at.exception, at.exception
    assert at.radio[0].options[0].startswith("✅ Awa Ndiaye")
    envoyes = json.loads((dossier / "factices" / "messagerie.json").read_text(encoding="utf-8"))["envoyes"]
    assert len(envoyes) == 1 and envoyes[0]["texte"] == texte
