"""GN-083: conservative match-phase detection from sequential narration windows.

All times are relative to the captured audio, never a scheduled kickoff or a
verified football clock. Strength levels are heuristic, not probabilities.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from hashlib import sha256
import math
import re
import unicodedata

from app.narration_classifier import NarrationLabel, classify_narration

PHASES = ("pre_game", "probable_start", "in_play", "half_time", "second_half")


def _fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(
        char for char in folded if not unicodedata.combining(char)
    )))


# Future tense and commentary about old games are not kickoff evidence.
_NOT_CURRENT = re.compile(
    r"\b(?:vai rolar|vai comecar|ira comecar|daqui a pouco|ja ja|"
    r"em instantes|prestes a|falta pouco|antes do jogo|antes da partida|"
    r"jogo anterior|partida anterior|na rodada passada|no ultimo jogo|"
    r"no jogo passado|nos melhores momentos|melhores momentos|"
    r"relembrando|recordando|ontem|semana passada|no aquecimento|"
    r"na simulacao|se comecasse|quando comecar|depois do intervalo|"
    r"apos o intervalo teremos|vai voltar|vai recome(c|ç)ar)\b"
)
_ADDITIONAL_BLOCK = re.compile(
    r"\b(?:propaganda|intervalo comercial|comercial|anuncio|"
    r"patrocinador|patrocinio|oferecimento|no replay|reprise|"
    r"melhores lances|ha pouco no jogo anterior)\b"
)
_FIRST_KICKOFF = re.compile(
    r"\b(?:comecou (?:o jogo|a partida|o primeiro tempo)|"
    r"comeca (?:o jogo|a partida|o primeiro tempo)|"
    r"apita (?:o arbitro|o juiz) (?:para )?(?:o inicio|comecando)|"
    r"(?:o arbitro|o juiz) apitou (?:para )?(?:o inicio|e comecou)|"
    r"autorizou (?:o inicio|a saida)|"
    r"deu (?:a )?saida (?:de bola|no meio campo)|"
    r"(?:esta|ta) valendo (?:o jogo|a partida)|"
    r"bola em jogo (?:agora|nesse momento)|"
    r"bola ja esta rolando|"
    r"(?:o )?(?:juiz|arbitro) apitou e (?:esta|ta) valendo(?: (?:o jogo|a partida))?)\b"
)
_SECOND_KICKOFF = re.compile(
    r"\b(?:comecou (?:o segundo tempo|a segunda etapa)|"
    r"comeca (?:o segundo tempo|a segunda etapa)|"
    r"reiniciou (?:o jogo|a partida)|"
    r"recomecou (?:o jogo|a partida)|"
    r"apita (?:o arbitro|o juiz) (?:para )?(?:o segundo tempo|a segunda etapa)|"
    r"(?:o arbitro|o juiz) apitou (?:para )?(?:o segundo tempo|a segunda etapa)|"
    r"bola rolando no segundo tempo|"
    r"deu (?:a )?saida (?:de bola )?para o segundo tempo)\b"
)
_HALF_STRONG = re.compile(
    r"\b(?:fim do primeiro tempo|termina o primeiro tempo|"
    r"terminou o primeiro tempo|acabou o primeiro tempo|"
    r"encerrou (?:o primeiro tempo|a primeira etapa)|"
    r"apitou (?:o fim|o final) (?:do primeiro tempo|da primeira etapa)|"
    r"apita (?:o fim|o final) (?:do primeiro tempo|da primeira etapa)|"
    r"apita para o intervalo|"
    r"final da primeira etapa)\b"
)
_HALF_WEAK = re.compile(
    r"\b(?:estamos no intervalo|agora no intervalo|"
    r"intervalo de jogo|intervalo da partida|"
    r"equipes no vestiario|primeiro tempo encerrado)\b"
)
_LIVE_CUES = (
    "recebe a bola", "com a bola", "bola com", "passa a bola",
    "toca de primeira", "rouba a bola", "recupera a bola",
    "cruza na area", "cruzou", "finaliza", "chutou", "chuta",
    "avanca pela direita", "avanca pela esquerda", "dispara pela esquerda",
    "cobrou o escanteio", "lateral para", "tiro de meta",
    "defendeu o chute", "falta em", "marcou o gol", "gol do",
    "carrega pela direita", "carrega pela esquerda", "carrega pelo meio",
    "carrega pelo lado direito", "carrega pelo lado esquerdo",
    "levando para a ponta esquerda", "levando para a ponta direita",
)

# Phase evidence only. These patterns never infer possession, player or zone.
# Football narration often omits the noun "bola", and ASR can alter grammatical
# gender ("ponta esquerdo"). Require a completed action + spatial football cue.
_SPATIAL_PLAY = re.compile(
    r"\b(?:carrega|carregando|leva|levando|avanca|avancando|toca|passa|joga|conduz|"
    r"recebe|recebeu|recebendo|retorna|retornando)\b.{0,64}?"
    r"\b(?:ponta (?:esquerd[ao]|direit[ao])|lado (?:esquerdo|direito)|"
    r"corredor (?:esquerdo|direito|central)|faixa (?:central|esquerda|direita)|grande area|"
    r"campo de (?:ataque|defesa))\b"
)
_PLAY_OUT = re.compile(r"\b(?:ja )?saiu jogando\b")
_UNCONFIRMED_ACTION = re.compile(r"\b(?:nao|nunca|jamais|poderia|teria|talvez|se tivesse)\b")


@dataclass(frozen=True, slots=True)
class PhaseEvidence:
    kind: str
    cue: str
    start_seconds: float
    end_seconds: float
    utterance_key: str = ""


class MatchStartDetector:
    """One detector per source: monotone transitions; evidence expires in audio time.

    A kickoff assertion alone stays provisional. Independent current-play
    narration must corroborate it, or three distinct current-play windows
    must corroborate each other if ASR missed the whistle.
    """

    def __init__(self) -> None:
        self.phase = "pre_game"
        self.confidence = "none"
        self.reason = "awaiting_current_play"
        self.first_play_audio_seconds: float | None = None
        self._start_had_kickoff = False
        self._recent: deque[PhaseEvidence] = deque(maxlen=16)
        self._last_sequence: int | None = None
        self._last_start: float | None = None
        self._last_signature: tuple[str, str] | None = None
        self._source_id: str | None = None

    @staticmethod
    def _is_blocked(text: str, folded: str) -> bool:
        if (_NOT_CURRENT.search(folded) or _ADDITIONAL_BLOCK.search(folded)
                or _UNCONFIRMED_ACTION.search(folded)):
            return True
        category = classify_narration(text).label
        return category in (
            NarrationLabel.AD, NarrationLabel.REPLAY,
            NarrationLabel.ANALYSIS, NarrationLabel.CONVERSATION,
        )

    @staticmethod
    def _current_play_cue(text: str, folded: str) -> str | None:
        if classify_narration(text).label == NarrationLabel.LIVE_PLAY:
            cue = next((cue for cue in _LIVE_CUES if cue in folded), None)
            if cue:
                return cue
        spatial = _SPATIAL_PLAY.search(folded)
        if spatial:
            return "spatial_current_play"
        if _PLAY_OUT.search(folded):
            return "played_out_from_defense"
        return None

    def _record(self, kind: str, cue: str, start: float, end: float, utterance_key: str = "") -> None:
        signature = kind, utterance_key or cue
        # Adjacent ASR windows may repeat a phrase. Overlap is not independent
        # evidence, even when sequence numbers differ.
        if signature == self._last_signature and self._recent and (
            start - self._recent[-1].start_seconds <= 12
        ):
            return
        self._last_signature = signature
        self._recent.append(PhaseEvidence(kind, cue, start, end, utterance_key))

    def _recent_kind(self, kind: str, at: float, window: float = 75) -> list[PhaseEvidence]:
        return [e for e in self._recent if e.kind == kind and 0 <= at - e.end_seconds <= window]

    def _confirm_play(self, at: float, *, second: bool) -> None:
        starts = self._recent_kind("second_start" if second else "first_start", at)
        plays = self._recent_kind("play", at)
        supported = bool(starts) and bool(plays) and any(
            p.end_seconds >= s.start_seconds for p in plays for s in starts
        )
        # Distinct narrations may legitimately use the SAME football verb.
        # Do not demand three different dictionary phrases; reject repeated text.
        independent = (len(plays) >= 3 and len({p.utterance_key for p in plays}) >= 3
                       and len({p.start_seconds for p in plays}) >= 3
                       and max(p.end_seconds for p in plays) - min(p.start_seconds for p in plays) >= 12)
        if not (supported or independent):
            if not second and starts and self.phase == "pre_game":
                self.phase = "probable_start"
                self.confidence = "low"
                self.reason = "kickoff_mentioned_waiting_for_live_play"
            return
        self.phase = "second_half" if second else "in_play"
        self.confidence = "high" if supported else "medium"
        self.reason = "kickoff_and_play" if supported else "multiple_independent_plays"
        if not second and self.first_play_audio_seconds is None:
            anchor = min(e.start_seconds for e in starts) if starts else plays[0].start_seconds
            self.first_play_audio_seconds = anchor
            self._start_had_kickoff = bool(starts)
        self._recent.clear()
        self._last_signature = None

    def consume(self, observation: dict) -> dict:
        """Advance on one sequential ASR transcript with audio-relative timestamps."""
        source = observation.get("source_id")
        seq = observation.get("sequence")
        start = observation.get("start_seconds")
        end = observation.get("end_seconds")
        text = observation.get("text")
        if (not isinstance(source, str) or not source.strip()
                or type(seq) is not int or seq < 0
                or type(start) not in (float, int) or type(end) not in (float, int)
                or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start <= end or not isinstance(text, str)
                or not text.strip() or len(text) > 2048):
            raise ValueError("Invalid GN-083 narration observation")
        if self._source_id is not None and self._source_id != source:
            raise ValueError("GN-083 detector cannot combine sources")
        if (self._last_sequence is not None and seq <= self._last_sequence
                or self._last_start is not None and start < self._last_start):
            raise ValueError("Out-of-order GN-083 narration observation")
        self._source_id = source
        self._last_sequence, self._last_start = seq, float(start)
        folded = _fold(text)
        if self._is_blocked(text, folded):
            return self.snapshot()
        utterance_key = sha256(folded.encode("utf-8")).hexdigest()

        # Half-time can only occur after established first-half play.
        if self.phase == "in_play":
            strong = _HALF_STRONG.search(folded)
            weak = _HALF_WEAK.search(folded)
            if strong or weak:
                self._record("half", "strong" if strong else "weak", start, end)
                if strong or len(self._recent_kind("half", end, 120)) >= 2:
                    self.phase, self.confidence = "half_time", "high" if strong else "medium"
                    self.reason = "first_half_end_narrated"
                    self._recent.clear()
                    self._last_signature = None
            return self.snapshot()

        if self.phase == "second_half":
            return self.snapshot()

        if self.phase == "half_time":
            second_cue = _SECOND_KICKOFF.search(folded)
            if second_cue:
                self._record("second_start", second_cue.group(), start, end)
            play = self._current_play_cue(text, folded)
            if play:
                self._record("play", play, start, end, utterance_key)
            self._confirm_play(end, second=True)
            return self.snapshot()

        first_cue = _FIRST_KICKOFF.search(folded)
        if first_cue:
            self._record("first_start", first_cue.group(), start, end)
        play = self._current_play_cue(text, folded)
        if play:
            self._record("play", play, start, end, utterance_key)
        self._confirm_play(end, second=False)
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "phase": self.phase,
            "confidence": self.confidence,
            "reason": self.reason,
            "first_play_audio_seconds": self.first_play_audio_seconds,
            "start_detection": "automatic_narration",
            "start_basis": ("kickoff_and_play" if self.first_play_audio_seconds is not None
                            and self._start_had_kickoff else "observed_play"
                            if self.first_play_audio_seconds is not None else None),
            "kickoff_time_verified": False,
            "ball_updates_allowed": self.phase in ("in_play", "second_half"),
            "recent_evidence": [asdict(e) for e in self._recent],
            "confidence_calibrated": False,
        }


def current_play_cue(text: str) -> str | None:
    """Read-only eligibility for other text evidence; never advances phase."""
    if not isinstance(text, str) or not text.strip() or len(text) > 2048:
        return None
    folded = _fold(text)
    if MatchStartDetector._is_blocked(text, folded):
        return None
    return MatchStartDetector._current_play_cue(text, folded)
