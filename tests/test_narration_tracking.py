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


@pytest.mark.parametrize("name,direction", [("Caio", "left_to_right"), ("Beto", "right_to_left")])
@pytest.mark.parametrize("side,lane", [("esquerda", "left"), ("direita", "right")])
def test_current_named_wing_is_an_estimated_attacking_area(name, direction, side, lane):
    region = track_narration(game(), f"{name} carrega levando para a ponta {side}.")[0]["region"]
    assert region["bands"] == [4, 5] and region["lane"] == lane
    assert region["attack_direction"] == direction
    assert region["depth_basis"] == "attacking_wing_estimate" and not region["exact_position"]


@pytest.mark.parametrize("area,bands", [
    ("no próprio campo", [1, 2]), ("no setor de defesa", [1, 2]),
    ("na defesa adversária", [4, 5]), ("no campo adversário", [4, 5]),
    ("na intermediária defensiva adversária", [4]),
])
def test_explicit_depth_overrides_wing_and_opponent_defense_is_attack(area, bands):
    region = track_narration(game(), f"Caio carrega na ponta esquerda {area}.")[0]["region"]
    assert region["bands"] == bands and region["depth_basis"] == "explicit_text"


def test_depth_context_is_short_same_player_and_resets_at_center_or_new_window():
    events = track_narration(game(), "Caio carrega na ponta esquerda, Caio carrega pelo lado esquerdo, Davi recebe pelo lado esquerdo, Caio recebe na faixa central, Caio carrega pelo lado esquerdo.")
    assert [event["region"]["bands"] for event in events] == [[4, 5], [4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5]]
    assert events[1]["region"]["depth_basis"] == "recent_same_player_context"
    assert track_narration(game(), "Caio carrega pelo lado esquerdo")[0]["region"]["bands"] == [1, 2, 3, 4, 5]


def test_recent_defensive_depth_wins_over_following_same_player_wing_estimate():
    events = track_narration(game(), "Caio recebe no próprio campo, Caio carrega pela ponta esquerda.")
    assert events[-1]["region"]["bands"] == [1, 2]


@pytest.mark.parametrize("already_second", [False, True])
def test_registry_second_half_changes_direction_only_when_not_already_configured(already_second):
    match = game()
    if already_second:
        match.period = "second_half"
        match.home.attack_direction = "right_to_left"
        match.away.attack_direction = "left_to_right"
    registry = LivePreviewRegistry()
    phrases = ["Começou o jogo", "Caio recebe a bola", "Termina o primeiro tempo, vamos ao intervalo",
               "Começa o segundo tempo", "Caio carrega levando para a ponta esquerda"]
    for seq, text in enumerate(phrases):
        view = registry.receive(match, LiveObservation(source_id="radio-one", sequence=seq,
            start_seconds=seq*10, end_seconds=seq*10+6, text=text, local_capture_age_seconds=0))
    assert view["phase"] == "second_half"
    assert view["latest_narration_action"]["region"]["attack_direction"] == "right_to_left"
    assert view["latest_narration_action"]["region"]["bands"] == [4, 5]


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


@pytest.mark.parametrize('text', ['Caio tocou a bola mais atrás.', 'Caio passa de primeira.',
    'Caio, entregou mais à frente ali.', 'Caio toca para Davi.'])
def test_named_distribution_requires_football_context_without_fabricating_receipt_or_zone(text):
    events = track_narration(game(), text)
    assert events[0]['player_id'] == 'caio' and events[0]['kind'] == 'ball_action'
    assert events[0]['region'] is None and not events[0]['touch_confirmed']


@pytest.mark.parametrize('text', ['Caio passou mal.', 'Caio tocou música.',
    'Caio entregou o prêmio para Davi.', 'Caio passa para a entrevista.',
    'Caio tocou música, Davi recebeu a bola?',
    'Caio não tocou a bola.', 'Caio vai passar a bola.',
    'No replay Caio entregou mais à frente.', 'Caio passa de primeira?'])
def test_generic_distribution_verbs_are_not_sufficient_for_a_football_action(text):
    assert track_narration(game(), text) == []


def test_distribution_cannot_borrow_the_ball_from_another_named_players_action():
    events = track_narration(game(), 'Caio tocou música, Davi recebe a bola.')
    assert any(e['player_id'] == 'davi' and e['kind'] == 'ball_action' for e in events)
    assert not any(e['player_id'] == 'caio' and e['kind'] == 'ball_action' for e in events)


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
