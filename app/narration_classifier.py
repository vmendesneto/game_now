"""GN-050: conservative, explainable pt-BR narration-type classification.

Text-only deterministic gate, not a trained model or football state extractor.
Ambiguous transcripts cannot directly update the live ball state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata


class NarrationKind(StrEnum):
    LIVE_PLAY = "live_play"
    AD = "ad"
    CONVERSATION = "conversation"
    ANALYSIS = "analysis"
    REPLAY = "replay"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NarrationDecision:
    kind: NarrationKind
    reason: str
    eligible_for_live_state: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "kind": self.kind.value,
            "reason": self.reason,
            "eligible_for_live_state": self.eligible_for_live_state,
        }


def _normalize(value: str) -> str:
    """Case/accent-fold without losing word boundaries (incl. ASR punctuation)."""
    folded = unicodedata.normalize("NFKD", value.casefold())
    letters = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", letters)).strip()


def _match(normalized: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(normalized) for pattern in patterns)


def _compile(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


# Priority of non-live rules is deliberate: a replay or ad may mention goals.
_AD = _compile(
    r"\b(?:oferecimento|patrocinad[oa]s?|patrocinio|apoio cultural|intervalo comercial)\b",
    r"\b(?:publicidade|anunciante|merchandising|nossos parceiros|mensagem comercial)\b",
    r"\b(?:compre agora|aproveite a promocao|cupom de desconto|acesse nosso site|ligue e compre)\b",
    r"\b(?:oferta imperdivel|preco especial|parcelamento sem juros)\b",
)
_REPLAY = _compile(
    r"\b(?:replay|reprise|repeticao|revendo o lance|rever o lance)\b",
    r"\b(?:olha de novo|veja de novo|vamos rever|vamos ver de novo|voltando ao lance)\b",
    r"\b(?:no lance anterior|na jogada anterior|instantes atras|ha pouco vimos|momento do gol anterior)\b",
)
_ANALYSIS = _compile(
    r"\b(?:na minha opiniao|na minha visao|ao meu ver|eu acho que|taticamente|analisando)\b",
    r"\b(?:analise do jogo|analise tatica|comentario tatico|olhando a estrategia)\b",
    r"\b(?:deveria ter|precisava ter|poderia ter|foi melhor no primeiro tempo)\b",
    r"\b(?:o time esta mal posicionado|o esquema tatico|avaliando a partida)\b",
)
_CONVERSATION = _compile(
    r"\b(?:bom dia pessoal|boa noite pessoal|tudo bem com voce|como vai voce|manda um abraco)\b",
    r"\b(?:um abraco para|obrigado pela audiencia|pergunta do ouvinte|mensagem do ouvinte)\b",
    r"\b(?:vamos conversar|voce esta nos ouvindo|quem esta acompanhando a transmissao)\b",
)
_LIVE = _compile(
    r"\b(?:bola com|bola para|bola na area|bola no meio|bola rolando|bola saiu|bola bate|bola passa|bola chegou|bola esta com)\b",
    r"\b(?:chuta|chutou|chute|finaliza|finalizou|finalizacao|cruza|cruzou|cruzamento|dribla|driblou)\b",
    r"\b(?:passa para|passou para|tocou para|recebeu a bola|roubou a bola|avanca com a bola|avancou com a bola)\b",
    r"\b(?:gol|golaco|escanteio|impedimento|penalti|tiro de meta)\b",
    r"\b(?:lateral para|falta sobre|defesa do goleiro|defendeu o goleiro|apita o arbitro)\b",
)


def classify_narration(text: str) -> NarrationDecision:
    """Classify one ASR segment; positive live label does NOT establish an event.

    GN-051+ must independently confirm entity, action, timing and field region.
    Mixed utterances with explicit non-live cues are blocked conservatively.
    """
    if not isinstance(text, str):
        raise TypeError("Narration text must be a string")
    normalized = _normalize(text)
    if not normalized:
        return NarrationDecision(NarrationKind.UNKNOWN, "empty_text", False)
    for kind, rules in (
        (NarrationKind.AD, _AD),
        (NarrationKind.REPLAY, _REPLAY),
        (NarrationKind.ANALYSIS, _ANALYSIS),
        (NarrationKind.CONVERSATION, _CONVERSATION),
    ):
        if _match(normalized, rules):
            return NarrationDecision(kind, f"{kind.value}_cue", False)
    if _match(normalized, _LIVE):
        return NarrationDecision(NarrationKind.LIVE_PLAY, "explicit_live_cue", True)
    return NarrationDecision(NarrationKind.UNKNOWN, "insufficient_evidence", False)
