"""Partial spatial language is not a complete/current ball-state assertion."""
import pytest

from app.contracts import Match, Player, Team
from app.gn083_live import LiveObservation, LivePreviewRegistry
from app.spatial_mentions import spatial_mention


def game(direction="left_to_right"):
    return Match(id="spatial-match", home=Team(id="azul", name="Azul", short_name="AZU",
        color="#112233", attack_direction=direction), away=Team(id="rubro", name="Rubro",
        short_name="RUB", color="#ff2233", attack_direction="right_to_left" if direction == "left_to_right" else "left_to_right"),
        players=[Player(id="caio", team_id="azul", name="Caio", number=9),
                 Player(id="beto", team_id="rubro", name="Beto", number=10)])


@pytest.mark.parametrize("direction", ["left_to_right", "right_to_left"])
def test_explicit_side_is_a_whole_corridor_without_longitudinal_band_or_possession(direction):
    result = spatial_mention(game(direction), "Caio do Azul carrega pelo lado esquerdo do gramado")
    assert result["status"] == "partial" and result["lane"] == "left"
    assert result["band"] is None and result["possession_confirmed"] is False
    assert result["team_id"] == "azul" and result["attack_direction"] == direction
    assert "player_id" not in result and "zone" not in result


def test_center_does_not_need_team_but_side_does_need_direction():
    result = spatial_mention(game(), "A equipe já saiu jogando no corredor central")
    assert result["status"] == "partial" and result["lane"] == "center" and result["team_id"] is None
    assert result["attack_direction"] is None
    result = spatial_mention(game(), "O atleta carrega levando pra ponta esquerdo do gramado")
    assert result["status"] == "unknown" and result["reason"] == "corridor_direction_unknown"


def test_conflicting_local_teams_cannot_orient_a_side_and_names_are_not_fuzzily_guessed():
    for text in ("Caio e Beto carrega pelo lado esquerdo do gramado",
                 "Caiozinho carrega pelo lado esquerdo do gramado"):
        assert spatial_mention(game(), text)["status"] == "unknown"


def test_uppercase_team_abbreviation_is_preserved_for_entity_resolution():
    assert spatial_mention(game(), "AZU com a bola pelo lado esquerdo")["team_id"] == "azul"
    assert spatial_mention(game(), "azu com a bola pelo lado esquerdo")["status"] == "unknown"


def test_text_order_is_only_a_last_mentioned_corridor_not_trajectory():
    result = spatial_mention(game(), "Caio carrega pelo lado esquerdo do gramado, depois cita a faixa central")
    assert result["lane"] == "center" and result["band"] is None
    assert result["basis"] == "last_corridor_mentioned_not_ball_position"


@pytest.mark.parametrize("prefix", ["Oferecimento", "No replay", "Ontem", "Daqui a pouco", "Talvez", "Na minha opinião", "Não"])
def test_partial_mentions_keep_existing_context_veto(prefix):
    assert spatial_mention(game(), prefix + ": Caio carrega pelo lado esquerdo do gramado")["status"] == "unknown"


def test_static_lineup_discussion_or_side_alone_does_not_highlight():
    for text in ("Caio ocupa o corredor central na formação", "Pelo lado esquerdo", "Caio tem camisa nove"):
        assert spatial_mention(game(), text)["status"] == "unknown"
    match = game()
    match.period = "half_time"
    assert spatial_mention(match, "Caio carrega pelo lado esquerdo do gramado")["status"] == "unknown"


def observation(seq, text, age=0):
    return LiveObservation(source_id="source-spatial", sequence=seq, start_seconds=seq * 6,
                           end_seconds=seq * 6 + 6, text=text, local_capture_age_seconds=age)


def test_recent_corridor_is_distinct_from_ball_and_clears_on_new_text_staleness_and_stop():
    clock = [0.]
    registry = LivePreviewRegistry(clock=lambda: clock[0])
    match = game()
    view = registry.receive(match, observation(0, "A equipe já saiu jogando no corredor central"))
    assert view["ball"] is None and view["spatial_mention"]["lane"] == "center"
    assert view["phase"] == "pre_game"  # A single mention does not seed phase.
    clock[0] = 16
    assert registry.get(match.id)["spatial_mention"] is None
    view = registry.receive(match, observation(1, "Caio carrega pelo lado esquerdo do gramado"))
    assert view["spatial_mention"]["lane"] == "left"
    view = registry.receive(match, observation(2, "Oferecimento de uma loja"))
    assert view["spatial_mention"] is None
    view = registry.receive(match, observation(3, "Caio carrega pelo lado esquerdo do gramado", age=6))
    assert view["spatial_mention"] is None
    registry.clear_match(match.id)
    assert registry.get(match.id) is None


def test_complete_ball_candidate_takes_priority_over_partial_corridor():
    registry = LivePreviewRegistry()
    match = game()
    registry.receive(match, observation(0, "Começou o jogo"))
    view = registry.receive(match, observation(1, "Caio do Azul com a bola no meio-campo pela direita"))
    assert view["ball"]["zone"] == {"band": 3, "lane": "right"}
    assert view["spatial_mention"] is None
