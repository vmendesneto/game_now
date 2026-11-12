"""Actions and participants must survive missing geography, without fake motion."""
import pytest

from app.contracts import Match, Player, Team
from app.gn083_live import LiveObservation, LivePreviewRegistry
from app.narration_tracking import track_narration


def game():
    return Match(id="tracking-match", home=Team(id="blue", name="Azul", short_name="AZU", color="#112233", attack_direction="left_to_right"),
                 away=Team(id="red", name="Rubro", short_name="RUB", color="#aabbcc", attack_direction="right_to_left"),
                 players=[Player(id="caio", name="Caio", number=8, team_id="blue"),
                          Player(id="davi", name="Davi", number=9, team_id="blue"),
                          Player(id="beto", name="Beto", number=10, team_id="red")])


def test_ordered_receivers_and_turnover_do_not_require_a_complete_zone():
    events = track_narration(game(), "Caio recebeu. Serve Davi. Davi domina. Beto recuperou.")
    assert [e["player_id"] for e in events] == ["caio", "davi", "davi", "beto"]
    assert [e["team_id"] for e in events] == ["blue", "blue", "blue", "red"]
    assert events[1]["kind"] == "pass_target"  # A target is not a verified reception.
    assert events[-1]["kind"] == "recovery"
    assert all(e["region"] is None and not e["audio_time_verified"] for e in events)


def test_player_team_pair_and_explicit_named_team_control():
    assert track_narration(game(), "Caio do Azul recebeu")[0]["player_id"] == "caio"
    event = track_narration(game(), "Fica no domínio da equipe do Rubro com Beto")[0]
    assert event["player_id"] == "beto" and event["team_id"] == "red"


@pytest.mark.parametrize("prefix", ["Ontem", "No replay", "Oferecimento", "Na minha opinião", "Taticamente", "Talvez", "Eu acredito que"])
def test_ads_replays_analysis_and_speculation_are_not_actions(prefix):
    assert track_narration(game(), prefix + ": Caio recebeu no meio-campo.") == []


@pytest.mark.parametrize("text", ["Caio não recebeu", "Caio vai receber", "Caio recebeu?", "Caio recebeu atendimento", "Caio recebeu cartão",
                                 "Caio e Davi", "Caiozinho recebeu", "Beto costuma jogar no corredor direito", "Caio poderia receber"])
def test_denied_future_unknown_names_and_non_ball_receipts_are_rejected(text):
    assert track_narration(game(), text) == []


def test_defender_mentioned_in_a_marking_phrase_is_not_the_next_passer():
    events = track_narration(game(), "Escapou da marcação do Beto, serve Caio.")
    assert len(events) == 1 and events[0]["player_id"] == "caio"
    assert events[0]["kind"] == "pass_target"


def test_partial_defense_midfield_attack_remain_areas_without_fake_lane():
    events = track_narration(game(), "Caio no setor de defesa domina. Davi recebe no meio-campo. Beto carrega para o campo de ataque.")
    assert [e["region"]["bands"] for e in events] == [[1, 2], [3], [4, 5]]
    assert all(e["region"]["lane"] is None and not e["region"]["exact_position"] for e in events)
    assert events[-1]["region"]["attack_direction"] == "right_to_left"


def test_geography_cannot_cross_another_named_player():
    events = track_narration(game(), "Caio carrega, Beto está no corredor direito.")
    assert len(events) == 1 and events[0]["region"] is None


def test_unresolved_ambiguous_names_do_not_fall_back_to_a_team():
    match = game()
    match.players.append(Player(id="other-caio", name="Caio", number=7, team_id="red"))
    assert track_narration(match, "Caio recebeu") == []


def test_registry_keeps_ordered_history_but_expires_current_actor_and_never_sets_ball():
    now = [0.]
    registry = LivePreviewRegistry(clock=lambda: now[0])
    view = registry.receive(game(), LiveObservation(source_id="radio-one", sequence=0, start_seconds=0,
        end_seconds=12, text="Caio recebeu. Serve Davi. Beto recuperou.", local_capture_age_seconds=2))
    assert len(view["narration_actions"]) == 3 and view["ball"] is None
    assert view["latest_narration_action"]["player_id"] == "beto"
    now[0] = 14
    view = registry.get(game().id)
    assert view["latest_narration_action"] is None and len(view["narration_actions"]) == 3
    registry.clear_match(game().id)
    assert registry.get(game().id) is None


def test_history_is_bounded_and_isolated_and_overlap_does_not_duplicate_identical_text():
    registry = LivePreviewRegistry()
    for seq in range(110):
        view = registry.receive(game(), LiveObservation(source_id="radio-one", sequence=seq,
            start_seconds=seq*20, end_seconds=seq*20+12, text="Caio recebeu.", local_capture_age_seconds=0))
    assert len(view["narration_actions"]) == 96
    assert len({e["id"] for e in view["narration_actions"]}) == len(view["narration_actions"])
    other = registry.receive(game(), LiveObservation(source_id="radio-two", sequence=0,
        start_seconds=0, end_seconds=12, text="Beto recuperou.", local_capture_age_seconds=0))
    assert len(other["narration_actions"]) == 1


def test_elliptical_current_sequence_keeps_teammates_spatial_return_and_no_defender_possession():
    text=("Vem Caio, chamando o Davi do lado esquerdo do campo, Davi já carrega, "
          "levando pra ponta esquerda, Beto trava a dele, Davi carrega, "
          "Caio na faixa central, devolviu pra Davi.")
    events=track_narration(game(),text)
    assert events[0]["player_id"]=="caio" and events[0]["kind"]=="named_sequence"
    assert not any(e["player_id"]=="beto" for e in events)
    assert any(e["player_id"]=="davi" and e["region"] and e["region"]["lane"]=="left" for e in events)
    central=next(e for e in events if e["player_id"]=="caio" and e["region"])
    assert central["region"]["lane"]=="center" and central["region"]["bands"]==[1,2,3,4,5]
    assert events[-1]["player_id"]=="davi" and events[-1]["kind"]=="pass_target"
    assert events[-1]["region"] is None
    assert all(not e["touch_confirmed"] and not e["audio_time_verified"] for e in events)


def test_names_in_lineup_or_off_ball_position_are_not_elliptical_touches():
    assert track_narration(game(),"Caio, Davi na faixa central") == []
    events=track_narration(game(),"Caio carrega, Davi está no corredor esquerdo")
    assert len(events)==1 and events[0]["player_id"]=="caio"


def test_preview_exposes_all_current_actions_in_order_without_granting_complete_ball_permission():
    registry=LivePreviewRegistry()
    view=registry.receive(game(),LiveObservation(source_id="radio-one",sequence=0,start_seconds=0,end_seconds=12,
        text="Caio carrega pelo lado esquerdo, Davi na faixa central, devolviu pra Caio",local_capture_age_seconds=1))
    assert [a["player_id"] for a in view["current_narration_actions"]]==["caio","davi","caio"]
    assert view["ball"] is None
    assert all(a["audio_start_seconds"]==0 and a["audio_end_seconds"]==12 for a in view["current_narration_actions"])
