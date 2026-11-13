from app.gn083_live import LiveObservation, LivePreviewRegistry
from tests.test_narration_tracking import game


def receive(registry, seq, text, *, source='source-one', age=0):
    return registry.receive(game(), LiveObservation(source_id=source, sequence=seq,
        start_seconds=seq*10, end_seconds=seq*10+12, text=text,
        local_capture_age_seconds=age))


def test_event_type_does_not_require_ball_position_and_never_changes_score():
    registry = LivePreviewRegistry(clock=lambda: 0.)
    match = game()
    original = match.model_dump()
    receive(registry, 0, 'Começou o jogo')
    view = receive(registry, 1, 'Caio chutou para o gol')
    assert view['phase'] == 'in_play'
    assert view['ball'] is None
    assert view['current_narrated_event']['kind'] == 'shot'
    assert view['current_narrated_event']['score_update_confirmed'] is False
    assert view['current_narrated_event']['audio_time_verified'] is False
    assert match.model_dump() == original


def test_replay_negation_ambiguity_and_unconfirmed_start_cannot_create_current_event():
    registry = LivePreviewRegistry(clock=lambda: 0.)
    assert receive(registry, 0, 'Caio chutou')['current_narrated_event'] is None
    receive(registry, 1, 'Começou o jogo')
    receive(registry, 2, 'Caio com a bola')
    for seq, text in enumerate(['No replay, Caio chutou', 'Caio não chutou',
                                'Caio chutou e o goleiro defendeu o chute', 'Caio chutou?'], start=3):
        assert receive(registry, seq, text)['current_narrated_event'] is None


def test_stale_event_remains_only_in_bounded_textual_history():
    now = [0.]
    registry = LivePreviewRegistry(clock=lambda: now[0])
    receive(registry, 0, 'Começou o jogo')
    receive(registry, 1, 'Caio chutou')
    now[0] = 16
    view = registry.get(game().id)
    assert view['current_narrated_event'] is None and len(view['narrated_events']) == 1
    for seq in range(2, 150):
        receive(registry, seq, 'Caio chutou')
    assert len(registry.get(game().id)['narrated_events']) == 96


def test_shared_interval_or_end_hides_an_old_sources_current_play():
    registry = LivePreviewRegistry(clock=lambda: 0.)
    registry.add_independent_sources(game().id, ['source-one', 'source-two'])
    for source in ('source-one', 'source-two'):
        receive(registry, 0, 'Começou o jogo', source=source)
        receive(registry, 1, 'Caio chutou', source=source)
    receive(registry, 2, 'Termina o primeiro tempo', source='source-one')
    view = registry.get(game().id)
    assert view['group_phase'] == 'half_time'
    assert view['current_narrated_event'] is None and view['current_narration_actions'] == []
    assert view['ball'] is None and view['ball_updates_allowed'] is False
