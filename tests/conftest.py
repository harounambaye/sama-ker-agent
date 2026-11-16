"""Fixtures communes. Les tests n'utilisent ni .env, ni réseau, ni clé API."""

from __future__ import annotations

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from agent.config import Config


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        model="modele-de-test", model_secours="", effort="medium",
        max_etapes=5, max_tokens_email=30_000, max_tokens_reponse=1_000,
        traces_dir=str(tmp_path / "traces"), checkpoint_db=str(tmp_path / "cp.sqlite"),
    )


def message(contenu, stop_reason: str, entree: int = 100, sortie: int = 20) -> Message:
    return Message(
        id="msg_test", type="message", role="assistant", model="modele-de-test",
        content=contenu, stop_reason=stop_reason, stop_sequence=None,
        usage=Usage(input_tokens=entree, output_tokens=sortie),
    )


def appel_outil(id_: str, nom: str, arguments: dict) -> ToolUseBlock:
    return ToolUseBlock(id=id_, type="tool_use", name=nom, input=arguments)


def texte(t: str) -> TextBlock:
    return TextBlock(type="text", text=t)


class FauxClient:
    """Rejoue une liste de réponses à la place de l'API du modèle."""

    def __init__(self, reponses):
        self._reponses = iter(reponses)
        self.requetes: list[dict] = []
        self.messages = self

    def create(self, **requete):
        self.requetes.append(requete)
        return next(self._reponses)
