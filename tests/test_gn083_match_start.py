"""GN-083: synthetic audio-relative phase detection. Not real ASR accuracy."""
from __future__ import annotations

import pytest

from app.match_start_detection import MatchStartDetector


def row(seq, text, *, start=None, source="source-083"):
    start = seq * 6.0 if start is None else start
    return {
        "source_id": source, "sequence": seq,
        "start_seconds": start, "end_seconds": start + 6.0, "text": text,
    }


def test_long_pregame_and_future_tense_never_start_game():
    detector = MatchStartDetector()
    for i in range(300):
        text = (
            "A bola vai rolar daqui a pouco, acompanhe o aquecimento"
            if i % 2 else "No último jogo o Cruzeiro marcou o gol com a bola na área"
        )
        result = detector.consume(row(i, text))
        assert result["phase"] == "pre_game"
        assert not result["ball_updates_allowed"]
    assert result["first_play_audio_seconds"] is None
    assert result["confidence"] == "none"


def test_whistle_needs_independent_play_then_allows_ball_updates():
    detector = MatchStartDetector()
    result = detector.consume(row(0, "O árbitro apitou para o início do jogo"))
    assert result["phase"] == "probable_start"
    assert result["confidence"] == "low"
    assert result["ball_updates_allowed"] is False
    result = detector.consume(row(
        1, "Cruzeiro com a bola no meio-campo pela direita",
    ))
    assert result["phase"] == "in_play"
    assert result["confidence"] == "high"
    assert result["first_play_audio_seconds"] == 0
    assert result["ball_updates_allowed"] is True


def test_false_starts_from_commercial_replays_and_history():
    detector = MatchStartDetector()
    snippets = [
        "Oferecimento: começou o jogo e Caio recebe a bola",
        "No replay o árbitro apitou para o início da partida",
        "Na rodada passada começou a partida e a bola rolou",
        "No jogo anterior o Bahia com a bola pela esquerda",
        "Daqui a pouco começa o jogo, a bola vai rolar",
        "Em instantes começou o primeiro tempo, foi um anúncio",
        "Taticamente o Cruzeiro com a bola no meio-campo",
    ]
    for seq, text in enumerate(snippets):
        assert detector.consume(row(seq, text))["phase"] == "pre_game"


def test_missing_whistle_needs_three_distinct_current_play_windows():
    detector = MatchStartDetector()
    assert detector.consume(row(0, "Cruzeiro com a bola"))["phase"] == "pre_game"
    assert detector.consume(row(1, "Caio recebe a bola"))["phase"] == "pre_game"
    result = detector.consume(row(2, "Caio chutou para o gol"))
    assert result["phase"] == "in_play"
    assert result["confidence"] == "medium"


def test_repeated_asr_phrase_is_not_independent_evidence():
    detector = MatchStartDetector()
    for i in range(3):
        assert detector.consume(row(i, "Cruzeiro com a bola"))["phase"] == "pre_game"
    assert detector.consume(row(3, "Bola com o Bahia"))["phase"] == "pre_game"


def test_halftime_and_second_half_confirmed_by_narration_not_time():
    detector = MatchStartDetector()
    detector.consume(row(0, "Começou o jogo"))
    detector.consume(row(1, "Cruzeiro recebe a bola"))
    for i in range(2, 310):
        detector.consume(row(i, "Narradores analisam as escalações e o confronto"))
    halftime = detector.consume(row(310, "Termina o primeiro tempo, vamos ao intervalo"))
    assert halftime["phase"] == "half_time"
    assert not halftime["ball_updates_allowed"]
    assert detector.consume(row(311, "O segundo tempo vai começar daqui a pouco"))["phase"] == "half_time"
    assert detector.consume(row(312, "Começa o segundo tempo"))["phase"] == "half_time"
    second = detector.consume(row(313, "Bahia com a bola pelo meio-campo"))
    assert second["phase"] == "second_half"
    assert second["confidence"] == "high"
    assert second["ball_updates_allowed"]
    assert second["first_play_audio_seconds"] == 0


def test_provisional_kickoff_expires_without_confirming_first_half():
    detector = MatchStartDetector()
    assert detector.consume(row(0, "Começou o jogo"))["phase"] == "probable_start"
    assert detector.consume(row(30, "O Bahia com a bola"))["phase"] == "probable_start"
    assert detector.consume(row(31, "Caio recebe a bola"))["phase"] == "probable_start"
    assert detector.consume(row(32, "Caio chutou"))["phase"] == "in_play"


def test_duplicate_or_reverse_timestamps_fail_closed():
    detector = MatchStartDetector()
    detector.consume(row(2, "Começou o jogo"))
    with pytest.raises(ValueError, match="Out-of-order"):
        detector.consume(row(2, "Cruzeiro com a bola"))
    with pytest.raises(ValueError, match="Out-of-order"):
        detector.consume(row(3, "Cruzeiro com a bola", start=0))


def test_first_half_not_confirmed_by_interval_or_second_half_words():
    detector = MatchStartDetector()
    assert detector.consume(row(0, "Termina o primeiro tempo"))["phase"] == "pre_game"
    assert detector.consume(row(1, "Começa o segundo tempo"))["phase"] == "pre_game"


def test_join_midgame_without_whistle_accepts_distinct_plays_using_the_same_cue():
    detector = MatchStartDetector()
    assert detector.consume(row(0, "Caio com a bola pela direita"))["phase"] == "pre_game"
    assert detector.consume(row(1, "Beto com a bola no campo de defesa"))["phase"] == "pre_game"
    result = detector.consume(row(2, "Davi com a bola perto da área"))
    assert result["phase"] == "in_play"
    assert result["reason"] == "multiple_independent_plays"
    assert result["confidence"] == "medium"


def test_colloquial_spatial_play_and_playing_out_confirm_midgame():
    # Invented wording, not a transcription/gold-label corpus from the source.
    detector = MatchStartDetector()
    samples = (
        "Caio carrega, levando pra ponta esquerdo do gramado",
        "Beto recebe e já saiu jogando para Davi",
        "Agora a equipe retomou, Davi já saiu jogando pela defesa",
    )
    for seq, text in enumerate(samples):
        result = detector.consume(row(seq, text, start=seq * 10))
    assert result["phase"] == "in_play"
    assert result["first_play_audio_seconds"] == 0  # first observed play, not actual kickoff


@pytest.mark.parametrize("prefix", ["No replay", "Ontem", "Daqui a pouco", "Talvez", "Na minha opinião", "Oferecimento"])
def test_new_midgame_cues_preserve_context_veto(prefix):
    detector = MatchStartDetector()
    for seq in range(4):
        text = f"{prefix}: atleta {seq} carrega levando pra ponta esquerda do gramado e já saiu jogando"
        assert detector.consume(row(seq, text))["phase"] == "pre_game"


def test_same_audio_interval_and_duplicate_wording_do_not_supply_independent_evidence():
    detector = MatchStartDetector()
    for seq, name in enumerate(("Caio", "Beto", "Davi")):
        assert detector.consume(row(seq, name + " com a bola", start=0))["phase"] == "pre_game"
    detector = MatchStartDetector()
    for seq, text in enumerate(("Caio já saiu jogando.", "CAIO JÁ SAIU JOGANDO!", "Caio  já saiu jogando")):
        assert detector.consume(row(seq, text))["phase"] == "pre_game"


def test_juiz_apitou_e_esta_valendo_is_provisional_until_current_play():
    detector = MatchStartDetector()
    assert detector.consume(row(0, "O juiz apitou e está valendo"))["phase"] == "probable_start"
    assert detector.consume(row(1, "Caio carrega levando pra ponta esquerda do gramado"))["phase"] == "in_play"
    detector = MatchStartDetector()
    assert detector.consume(row(0, "Não é verdade que o juiz apitou e está valendo"))["phase"] == "pre_game"


def test_phase_detector_cannot_mix_sources_or_accept_infinite_times():
    detector = MatchStartDetector()
    detector.consume(row(0, "Caio com a bola"))
    with pytest.raises(ValueError, match="combine sources"):
        detector.consume(row(1, "Beto com a bola", source="other-source"))
    with pytest.raises(ValueError, match="Invalid"):
        MatchStartDetector().consume(row(0, "Começou o jogo", start=float("inf")))


def test_receiving_and_returning_with_spatial_narration_can_confirm_play_without_whistle():
    detector = MatchStartDetector()
    for seq, text in enumerate([
        'Caio carrega pela ponta esquerda',
        'Beto já saiu jogando pela defesa',
        'Davi recebeu, tenta o lançamento para o campo de ataque',
    ]):
        result = detector.consume(row(seq, text, start=seq*10))
    assert result['phase'] == 'in_play'
    assert result['start_basis'] == 'observed_play'
    assert result['kickoff_time_verified'] is False


@pytest.mark.parametrize('text', [
    'Caio recebeu, tenta o lançamento para o campo de ataque',
    'Beto retorna o jogo para o lado esquerdo',
])
@pytest.mark.parametrize('prefix', ['Não', 'Talvez', 'Ontem', 'No replay', 'Oferecimento', 'Daqui a pouco'])
def test_added_spatial_phase_cues_cannot_override_negative_or_noncurrent_context(text, prefix):
    detector = MatchStartDetector()
    for seq in range(4):
        assert detector.consume(row(seq, f'{prefix}: {text}'))['phase'] == 'pre_game'


def test_complete_match_cycle_with_delayed_start_break_extra_time_and_full_time():
    detector = MatchStartDetector()
    seq, audio = 0, 0.

    def advance(text, duration=10):
        nonlocal seq, audio
        result = detector.consume({'source_id': 'complete-source', 'sequence': seq,
            'start_seconds': audio, 'end_seconds': audio+duration, 'text': text})
        seq += 1
        audio += duration
        return result

    for _ in range(30):
        assert advance('A partida vai começar daqui a pouco')['phase'] == 'pre_game'
    advance('Começou o jogo')
    assert advance('Caio com a bola pela direita')['phase'] == 'in_play'
    for _ in range(300):
        assert advance('Beto carrega pela esquerda')['phase'] == 'in_play'
    assert advance('Termina o primeiro tempo')['phase'] == 'half_time'
    for _ in range(90):
        assert advance('Equipes no vestiário')['phase'] == 'half_time'
    advance('Começa o segundo tempo')
    assert advance('Davi com a bola pelo meio')['phase'] == 'second_half'
    for _ in range(300):
        assert advance('Caio carrega pela direita')['phase'] == 'second_half'
    result = advance('O árbitro apitou o final do jogo, partida encerrada')
    assert result['phase'] == 'finished' and not result['ball_updates_allowed']
    assert audio > 7200  # virtual audio timeline, no physical two-hour claim
    assert advance('Caio com a bola')['phase'] == 'finished'


@pytest.mark.parametrize('prefix', ['No replay', 'Ontem', 'Oferecimento', 'Não', 'Talvez'])
def test_noncurrent_full_time_cannot_end_match(prefix):
    detector = MatchStartDetector()
    detector.consume(row(0, 'Começou o jogo'))
    detector.consume(row(1, 'Caio com a bola'))
    assert detector.consume(row(2, prefix+': terminou o jogo'))['phase'] == 'in_play'


def test_full_time_is_not_inferred_from_elapsed_time_or_before_start():
    detector = MatchStartDetector()
    assert detector.consume(row(0, 'Fim de jogo'))['phase'] == 'pre_game'
    detector.consume(row(1, 'Começou o jogo'))
    detector.consume(row(2, 'Caio com a bola'))
    assert detector.consume(row(3, 'Narradores analisam o confronto', start=15000))['phase'] == 'in_play'


def test_question_about_referee_full_time_cannot_end_the_match():
    detector = MatchStartDetector()
    detector.consume(row(0, 'Começou o jogo'))
    detector.consume(row(1, 'Caio com a bola'))
    result = detector.consume(row(2, 'O árbitro apitou o final do jogo?'))
    assert result['phase'] == 'in_play' and result['ball_updates_allowed']


@pytest.mark.parametrize('whistle', ['agora apita', 'agora a pita'])
def test_immediate_kickoff_announcement_needs_subsequent_ball_circulation(whistle):
    detector = MatchStartDetector()
    assert detector.consume(row(0, 'E '+whistle+'! Início de jogo no estádio.'))['phase'] == 'probable_start'
    result = detector.consume(row(1, 'A equipe vem pelo meio tocando bola.'))
    assert result['phase'] == 'in_play' and result['start_basis'] == 'kickoff_and_play'
    assert result['kickoff_time_verified'] is False


@pytest.mark.parametrize('prefix', ['No replay', 'Ontem', 'Oferecimento', 'Não', 'Talvez', 'Daqui a pouco'])
def test_ball_circulation_and_kickoff_cannot_override_noncurrent_context(prefix):
    detector = MatchStartDetector()
    for seq, text in enumerate(['agora apita início de jogo', 'o time está tocando bola',
                              'segue rodando a bola', 'vem circulando a bola']):
        assert detector.consume(row(seq, prefix+': '+text))['phase'] == 'pre_game'


def test_present_tense_half_end_and_second_half_restart_with_asr_gender_variation():
    detector = MatchStartDetector()
    detector.consume(row(0, 'Começou o jogo'))
    detector.consume(row(1, 'Caio com a bola'))
    result = detector.consume(row(2, 'E acaba agora o primeiro tempo, o treinador vai conversar com o pessoal.'))
    assert result['phase'] == 'half_time'
    result = detector.consume(row(3, 'Estamos nas emoções do segundo tempo. O Azul dá a saída de bola e vai tocando o bola ali atrás.'))
    assert result['phase'] == 'second_half'
    result = detector.consume(row(4, 'Fim de jogo no estádio.'))
    assert result['phase'] == 'finished'


@pytest.mark.parametrize('prefix', ['No replay', 'Ontem', 'Oferecimento', 'Não', 'Talvez'])
def test_present_tense_half_end_does_not_override_vetoes(prefix):
    detector = MatchStartDetector()
    detector.consume(row(0, 'Começou o jogo'))
    detector.consume(row(1, 'Caio com a bola'))
    assert detector.consume(row(2, prefix+': acaba agora o primeiro tempo'))['phase'] == 'in_play'


def test_question_about_half_end_cannot_confirm_interval():
    detector = MatchStartDetector()
    detector.consume(row(0, 'Começou o jogo'))
    detector.consume(row(1, 'Caio com a bola'))
    assert detector.consume(row(2, 'Acaba agora o primeiro tempo?'))['phase'] == 'in_play'
