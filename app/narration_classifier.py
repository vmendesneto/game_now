"""GN-050: deterministic, conservative narration category baseline.

This is a rule-based classifier, not a probabilistic language model. Its labels
do not imply ball location, player identity, event extraction or match time.
The v1 event contract intentionally lacks "conversation": the safe adapter
maps that internal label to Category.UNKNOWN until a contract revision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from app.contracts import Category

MAX_TEXT_CHARS = 2048


class NarrationLabel(StrEnum):
    LIVE_PLAY = "live_play"
    AD = "ad"
    CONVERSATION = "conversation"
    ANALYSIS = "analysis"
    REPLAY = "replay"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NarrationDecision:
    label: NarrationLabel
    matched_cue: str | None

    @property
    def is_current_play(self) -> bool:
        """Only explicit live-play cues may be candidates for later NLP."""
        return self.label == NarrationLabel.LIVE_PLAY


# Priority matters. An ad mentioning "gol" must not become a live event;
# an analyst talking about a replay must not move the ball.
CUES: tuple[tuple[NarrationLabel, tuple[str, ...]], ...] = (
    (NarrationLabel.AD, (
        "oferecimento", "patrocinador", "patrocinio", "apoio cultural",
        "promocao", "desconto", "oferta", "ofertas", "compre agora",
        "visite nossa loja", "publicidade", "anunciante", "cupom",
    )),
    (NarrationLabel.REPLAY, (
        "no replay", "o replay mostra", "na repeticao", "na reprise",
        "revendo o lance", "vamos rever", "lance anterior",
        "vamos ver de novo", "imagem do lance passado",
    )),
    (NarrationLabel.ANALYSIS, (
        "na minha opiniao", "taticamente", "deveria ter",
        "o treinador precisa", "analisando a partida", "esquema tatico",
        "fazendo uma analise", "se tivesse", "poderia ter sido",
        "o time errou na marcacao", "avaliando o jogo",
    )),
    (NarrationLabel.CONVERSATION, (
        "boa noite", "bom dia", "boa tarde", "meu amigo", "um abraco",
        "qual sua opiniao", "o que voce acha", "concordo com voce",
        "obrigado pela audiencia", "alo torcida", "como vai",
        "estou te ouvindo", "mande seu recado",
    )),
    (NarrationLabel.LIVE_PLAY, (
        "recebe a bola", "passa a bola", "com a bola",
        "cruza na area", "cruza para a area", "cruzou",
        "finaliza", "chutou", "chuta", "cobrou o escanteio",
        "marcou o gol", "gol do", "goool", "gooool", "defendeu o chute",
        "goleiro defendeu", "impedimento marcado", "lateral para",
        "falta em", "penalti para", "tiro de meta", "bola rolando",
        "toca de primeira", "avanca pela direita", "dispara pela esquerda",
        "escanteio para", "defesa do goleiro", "comete a falta",
    )),
)


def _normalize(text: str) -> str:
    no_accents = "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", no_accents))


def classify_narration(text: str) -> NarrationDecision:
    """Classify explicit cues, defaulting ambiguous text to UNKNOWN.

    No inferred confidence: cue matches in this small hand-labeled baseline
    are not calibrated probabilities. Input is bounded and purely textual.
    """
    if not isinstance(text, str):
        raise TypeError("Narration text must be a string")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Narration text exceeds maximum length")
    normalized = _normalize(text)
    if not normalized:
        return NarrationDecision(NarrationLabel.UNKNOWN, None)
    padded = " " + normalized + " "
    for label, phrases in CUES:
        for phrase in phrases:
            if " " + phrase + " " in padded:
                return NarrationDecision(label, phrase)
    # Elongated football calls such as "GOOOOOL" are variable-length;
    # check after ads/replays to avoid moving the ball for a promotion.
    if any(re.fullmatch(r"go{3,}l", word) for word in normalized.split()):
        return NarrationDecision(NarrationLabel.LIVE_PLAY, "elongated_goal")
    return NarrationDecision(NarrationLabel.UNKNOWN, None)


def to_contract_category(label: NarrationLabel) -> Category:
    """Map the extra internal conversation label without altering schema v1."""
    if label == NarrationLabel.CONVERSATION:
        return Category.UNKNOWN
    return Category(label.value)
