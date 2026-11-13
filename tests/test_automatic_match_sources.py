"""Scheduled time is metadata; independent narrations decide whether play began."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.asr import BYTES_PER_SECOND
from app.capture_runtime import CaptureRequest
from app.gn083_live import LiveObservation, LivePreviewRegistry
from app.main import create_app
from tests.test_capture_runtime import BASE, MATCH, SOURCE, setup, until
from tests.test_narration_tracking import game


@pytest.mark.parametrize("scheduled", ["2026-11-13T20:00:00-03:00", "2035-11-13T20:00:00-03:00"])
def test_schedule_survives_restart_and_never_starts_match_or_changes_v1_state(tmp_path, scheduled):
    path = tmp_path / "schedule.sqlite3"
    with TestClient(create_app(path)) as client:
        assert client.post('/api/matches', json={**MATCH, 'scheduled_kickoff_at': scheduled}).status_code == 201
        schedule = client.get(BASE + '/schedule').json()
        assert schedule['scheduled_kickoff_at'].endswith('23:00:00+00:00')
        assert schedule['schedule_confirms_start'] is False
        before = client.get(BASE + '/state').json()
        assert 'scheduled_kickoff_at' not in before['match']
        assert client.get(BASE + '/live/preview').json() is None
        assert client.put(BASE, json=MATCH).status_code == 200  # old editor preserves schedule
        assert client.get(BASE + '/schedule').json() == schedule
    with TestClient(create_app(path)) as client:
        assert client.get(BASE + '/schedule').json() == schedule
        assert client.get(BASE + '/state').json() == before
        assert client.put(BASE, json={**MATCH, 'scheduled_kickoff_at': None}).status_code == 200
        assert client.get(BASE + '/schedule').json()['scheduled_kickoff_at'] is None
        assert client.delete(BASE).status_code == 204
        assert client.get(BASE + '/schedule').status_code == 404


@pytest.mark.parametrize('value', ['2026-11-13T20:00:00', 'invalid', True])
def test_schedule_requires_date_time_and_timezone(tmp_path, value):
    with TestClient(create_app(tmp_path / 'invalid.sqlite3')) as client:
        assert client.post('/api/matches', json={**MATCH, 'scheduled_kickoff_at': value}).status_code == 422


def test_long_delay_and_missing_whistle_are_detected_from_play_not_scheduled_time():
    registry = LivePreviewRegistry(clock=lambda: 0)
    registry.add_independent_sources(game().id, ['radio-one', 'radio-two', 'radio-three'])
    for seq in range(60):
        registry.receive(game(), LiveObservation(source_id='radio-one', sequence=seq,
            start_seconds=seq*6, end_seconds=seq*6+6,
            text='A partida vai começar daqui a pouco, aguardamos as equipes'))
        view = registry.get(game().id)
        assert view['group_phase'] == 'pre_game' and view['ball'] is None
    for seq, text in enumerate(['Caio com a bola pela direita', 'Beto com a bola no campo de defesa',
                               'Davi com a bola perto da área'], start=60):
        registry.receive(game(), LiveObservation(source_id='radio-one', sequence=seq,
            start_seconds=seq*6, end_seconds=seq*6+6, text=text))
    view = registry.get(game().id)
    assert view['phase'] == view['group_phase'] == 'in_play'
    assert view['start_detection'] == 'automatic_narration'
    assert view['start_basis'] == 'observed_play'
    assert view['first_play_audio_seconds'] == 360
    assert view['kickoff_time_verified'] is False


def test_variable_sources_dynamic_add_stop_restart_and_registration_keep_peers(tmp_path):
    calls, closed = [], []

    async def runner(url, match, **kwargs):
        ident = kwargs['source_id']
        calls.append(ident)
        try:
            kwargs['on_pcm'](12 * BYTES_PER_SECOND)
            for seq, text in enumerate(['Começou o jogo', 'Azul com a bola no meio-campo pela direita']):
                await kwargs['on_observation']({'source_id': ident, 'sequence': seq,
                    'start_seconds': seq*6, 'end_seconds': seq*6+6, 'text': text})
            await asyncio.Event().wait()
        finally:
            closed.append(ident)

    sources = [{**SOURCE, 'id': f'source-{i:02}', 'kind': 'radio' if i % 2 else 'youtube',
                'url': 'https://radio.example.org/audio.mp3' if i % 2 else SOURCE['url']} for i in range(12)]
    request = {'source_id': sources[0]['id'], 'permission_confirmed': True,
               'parallel_sources': [{'source_id': item['id']} for item in sources[1:]]}
    with TestClient(create_app(tmp_path / 'many.sqlite3', capture_runner=runner)) as client:
        setup(client)
        assert client.put(BASE + '/sources', json=sources).status_code == 200
        before = client.get(BASE + '/state').json()
        assert client.post(BASE + '/capture/start', json=request).status_code == 202
        deadline = time.monotonic()+3
        while client.get(BASE + '/capture').json()['observations'] < 24:
            assert time.monotonic() < deadline
            time.sleep(.01)
        status = until(client, 'running')
        assert len(status['streams']) == 12 and status['captured_seconds'] == 12
        assert len(client.get(BASE + '/transcripts').json()['sources']) == 12
        view = client.get(BASE + '/live/preview').json()
        assert view['group_phase'] == 'in_play'
        assert view['fusion']['source_count'] == 12
        assert view['fusion']['alignment_basis'] == 'independent_sources'
        assert view['fusion']['cross_source_chronology_verified'] is False
        assert client.get(BASE + '/state').json() == before
        new_source = {**SOURCE, 'id': 'source-extra'}
        assert client.put(BASE + '/sources', json=sources+[new_source]).status_code == 200
        assert client.put(BASE + '/sources', json=sources[1:]+[new_source]).status_code == 409
        extra = {'source_id': new_source['id'], 'permission_confirmed': True}
        assert client.post(BASE + '/capture/add', json={**extra, 'model': 'small'}).status_code == 409
        assert client.post(BASE + '/capture/add', json=extra).status_code == 202
        assert client.post(BASE + '/capture/add', json=extra).status_code == 409
        source_id = sources[0]['id']
        assert client.post(BASE + f'/capture/sources/{source_id}/stop').status_code == 202
        deadline = time.monotonic()+3
        while source_id not in closed:
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert client.get(BASE + '/capture').json()['observations'] >= 24
        assert client.get(BASE + '/live/preview').json()['fusion']['active_source_id'] != source_id
        assert client.post(BASE + '/capture/add', json={'source_id': source_id,
            'permission_confirmed': True}).status_code == 202
        deadline = time.monotonic()+3
        while calls.count(source_id) < 2 or any(s['state'] == 'starting' for s in client.get(BASE+'/capture').json()['streams']):
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert len(client.get(BASE + '/transcripts').json()['sources']) == 13
        assert all(s['error_code'] is None for s in client.get(BASE + '/capture').json()['streams'])
        client.post(BASE + '/capture/stop')
        until(client, 'stopped')
    assert len(calls) == len(closed) == 14


def test_unsynchronized_failover_never_inherits_region_or_clock_from_other_source():
    registry = LivePreviewRegistry(clock=lambda: 0)
    registry.add_independent_sources(game().id, ['source-one', 'source-two', 'source-three'])
    def receive(source, seq, text, start):
        registry.receive(game(), LiveObservation(source_id=source, sequence=seq,
            start_seconds=start, end_seconds=start+6, text=text))
    receive('source-one', 0, 'Começou o jogo', 100)
    receive('source-one', 1, 'Caio com a bola no meio-campo pela direita', 106)
    first = registry.get(game().id)
    receive('source-two', 0, 'Beto recebeu', 0)
    receive('source-one', 2, 'Oferecimento: uma loja', 112)
    second = registry.get(game().id)
    assert second['source_id'] == 'source-two'
    assert second['visual_context'] != first['visual_context']
    assert second['ball'] is None and second['latest_narration_region_action'] is None
    assert second['visual_timeline'] == 6
    assert second['ball_updates_allowed'] is False  # shared phase cannot authorize this source


def test_optional_recording_anchors_accept_many_sources_but_reject_duplicates_or_partial_anchors():
    sources = [{'source_id': f'other-{i}', 'start_seconds': 100+i, 'kickoff_seconds': 90+i} for i in range(20)]
    assert len(CaptureRequest(source_id='primary', permission_confirmed=True,
        start_seconds=20, kickoff_seconds=10, parallel_sources=sources).parallel_sources) == 20
    for extra in ([{'source_id': 'primary'}], [{'source_id': 'other', 'kickoff_seconds': 0}]):
        with pytest.raises(ValueError):
            CaptureRequest(source_id='primary', permission_confirmed=True, parallel_sources=extra)


def test_many_workers_share_one_model_and_serial_cpu_gate(tmp_path, monkeypatch):
    from app.asr import ASRResult
    from app.gn083_live import follow_youtube_narration
    import app.capture_runtime as module
    import threading
    made, prepared = [], []
    active, maximum = [0], [0]
    lock = threading.Lock()

    class Model:
        def __init__(self, settings):
            made.append(self)
        def prepare(self):
            prepared.append(self)
            time.sleep(.01)
        def transcribe_pcm(self, pcm):
            with lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
            try:
                time.sleep(.01)
                return ASRResult(model='base', language='pt', seconds=len(pcm)/BYTES_PER_SECOND,
                    text='Azul com a bola', segments=())
            finally:
                with lock:
                    active[0] -= 1

    async def capture(*args, **kwargs):
        for _ in range(12):
            yield b'\x01\x02'*8000
            await asyncio.sleep(.001)

    async def runner(*args, **kwargs):
        return await follow_youtube_narration(*args, **kwargs)

    monkeypatch.setattr(module, 'CPUTranscriber', Model)
    monkeypatch.setattr(module, 'asr_diagnostics', lambda: {'installed': True})
    monkeypatch.setattr(module.shutil, 'which', lambda name: name)
    monkeypatch.setattr(module, 'youtube_pcm_chunks', capture)
    app = create_app(tmp_path/'shared.sqlite3', capture_runner=runner)
    app.state.capture_runtime.check_tools = True
    with TestClient(app) as client:
        setup(client)
        sources = [{**SOURCE, 'id': f'shared-{i}'} for i in range(10)]
        client.put(BASE+'/sources', json=sources)
        assert client.post(BASE+'/capture/start', json={'source_id': sources[0]['id'],
            'parallel_sources': [{'source_id': item['id']} for item in sources[1:]],
            'permission_confirmed': True, 'seconds': 6, 'window_seconds': 6}).status_code == 202
        status = until(client, 'finished')
        assert len(status['streams']) == 10 and status['observations'] == 10
        assert len(made) == len(prepared) == maximum[0] == 1
        assert not app.state.capture_runtime.resources


def test_full_cpu_queue_fails_explicitly_and_closes_capture_instead_of_growing():
    from app.gn083_live import ASRCapacityError, follow_youtube_narration
    closed = []

    async def capture(*args, **kwargs):
        try:
            for _ in range(100):
                yield b'\x01\x02'*8000
                await asyncio.sleep(0)
        finally:
            closed.append(True)

    async def listener(row):
        pytest.fail('Recognition cannot run while CPU gate is unavailable')

    async def scenario():
        with pytest.raises(ASRCapacityError, match='bounded PCM buffer'):
            await asyncio.wait_for(follow_youtube_narration(SOURCE['url'], game(),
                max_seconds=60, on_observation=listener, capture_factory=capture,
                transcriber=object(), cpu_gate=asyncio.Semaphore(0)), timeout=2)
    asyncio.run(scenario())
    assert closed == [True]


def test_schedule_is_included_in_backup_restore(tmp_path):
    from app.configuration import MatchConfig
    from app.storage import SQLiteStore
    from scripts.gn092_backup import create_backup, restore_backup
    store = SQLiteStore(tmp_path/'original.sqlite3')
    store.create_match(MatchConfig.model_validate({**MATCH,
        'scheduled_kickoff_at': '2026-11-13T20:00:00-03:00'}))
    archive = tmp_path/'backup.zip'
    create_backup(store.path, archive)
    restored = tmp_path/'restored.sqlite3'
    restore_backup(archive, restored)
    assert SQLiteStore(restored).get_schedule(MATCH['id']) == store.get_schedule(MATCH['id'])
