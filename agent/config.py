"""Configuration de l'agent, lue depuis .env. Aucun modèle en dur dans le code."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    model: str
    model_secours: str
    effort: str
    max_etapes: int
    max_tokens_email: int
    max_tokens_reponse: int
    traces_dir: str
    checkpoint_db: str


def _obligatoire(nom: str) -> str:
    valeur = os.getenv(nom, "").strip()
    if not valeur:
        sys.exit(f"Variable {nom} absente du fichier .env (voir .env.example).")
    return valeur


def charger() -> Config:
    return Config(
        model=_obligatoire("MODEL"),
        model_secours=os.getenv("MODEL_SECOURS", ""),
        effort=os.getenv("EFFORT", "medium"),
        max_etapes=int(os.getenv("MAX_ETAPES", "12")),
        max_tokens_email=int(os.getenv("MAX_TOKENS_PAR_EMAIL", "30000")),
        max_tokens_reponse=int(os.getenv("MAX_TOKENS_REPONSE", "16000")),
        traces_dir=os.getenv("TRACES_DIR", "traces/brutes"),
        checkpoint_db=os.getenv("CHECKPOINT_DB", "data/checkpoints.sqlite"),
    )
