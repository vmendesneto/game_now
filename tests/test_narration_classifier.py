"""GN-050: original, hand-labeled Portuguese baseline; no live-audio claims."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from app.contracts import Category
from app.narration_classifier import (
    MAX_TEXT_CHARS, NarrationLabel, classify_narration, to_contract_category,
)

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "narration_labeled.json"


def test_every_original_labeled_sentence_matches_conservative_baseline():
    samples = json.loads(CORPUS.read_text(encoding="utf-8"))
    ids = [sample["id"] for sample in samples]
    assert len(ids) == len(set(ids))
    counts = Counter(sample["label"] for sample in samples)
    assert set(counts) == {label.value for label in NarrationLabel}
    assert all(count >= 6 for count in counts.values())
    errors = []
    for sample in samples:
        decision = classify_narration(sample["text"])
        if decision.label.value != sample["label"]:
            errors.append((sample["id"], sample["label"], decision.label.value))
        assert decision.is_current_play == (decision.label == NarrationLabel.LIVE_PLAY)
        assert (decision.matched_cue is not None) == (
            decision.label != NarrationLabel.UNKNOWN
        )
    assert not errors, errors


def test_no_event_assumptions_from_ambiguous_or_historical_speech():
    for text in (
        "Ele talvez esteja com a posse.",
        "Foi um gol no jogo da semana passada.",
        "O goleiro comentou a tática.",
        "Goleadas acontecem.",
        "",
        "   ...   ",
    ):
        decision = classify_narration(text)
        assert decision.label == NarrationLabel.UNKNOWN
        assert not decision.is_current_play


def test_ad_replay_and_analysis_override_goal_or_lance_cues():
    assert classify_narration("Promoção: quem fizer gol ganha desconto!").label == NarrationLabel.AD
    assert classify_narration("No replay, o atacante chutou para o gol.").label == NarrationLabel.REPLAY
    assert classify_narration("Na minha opinião, o atacante chutou cedo demais.").label == NarrationLabel.ANALYSIS


def test_portuguese_accents_case_and_phrase_boundaries():
    assert classify_narration("  PÊNALTI para o time visitante!!! ").label == NarrationLabel.LIVE_PLAY
    assert classify_narration("APOIO CULTURAL aos torcedores").label == NarrationLabel.AD
    assert classify_narration("Repetição sem palavras-chave").label == NarrationLabel.UNKNOWN
    assert classify_narration("Uma golada de água").label == NarrationLabel.UNKNOWN


def test_safe_mapping_preserves_frozen_contract_v1():
    assert to_contract_category(NarrationLabel.CONVERSATION) == Category.UNKNOWN
    assert to_contract_category(NarrationLabel.LIVE_PLAY) == Category.LIVE_PLAY
    assert to_contract_category(NarrationLabel.AD) == Category.AD
    assert to_contract_category(NarrationLabel.REPLAY) == Category.REPLAY
    assert to_contract_category(NarrationLabel.ANALYSIS) == Category.ANALYSIS


def test_text_bounds_and_input_types():
    with pytest.raises(TypeError, match="string"):
        classify_narration(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="maximum length"):
        classify_narration("x" * (MAX_TEXT_CHARS + 1))
    assert classify_narration("x" * MAX_TEXT_CHARS).label == NarrationLabel.UNKNOWN


@pytest.mark.parametrize("text", [
    "Caio carrega pela direita", "Beto carrega pelo meio",
    "O atacante carrega pelo lado esquerdo",
    "Ele segue levando para a ponta esquerda do gramado",
])
def test_explicit_current_spatial_actions_are_narration_without_implying_ball_position(text):
    assert classify_narration(text).label == NarrationLabel.LIVE_PLAY


@pytest.mark.parametrize("text,label", [
    ("Ontem, Caio carrega pela direita", "unknown"),
    ("No jogo anterior ele carrega pelo meio", "unknown"),
    ("Amanhã ele vai carregar pela direita", "unknown"),
    ("No replay ele carrega pela esquerda", "replay"),
    ("Promoção: ele carrega pela direita", "ad"),
    ("Na minha opinião ele carrega pelo meio", "analysis"),
    ("Ele carrega uma mochila", "unknown"),
    ("Essa ponta esquerda é do móvel", "unknown"),
])
def test_spatial_actions_keep_context_priority_and_abstain_on_unrelated_words(text, label):
    assert classify_narration(text).label.value == label
