"""Operational measurements retain bounded metadata, never content or accuracy."""
import asyncio
import json
import math
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.capture_metrics import CaptureMetrics, DelayDistribution
from app.main import create_app
from tests.test_capture_runtime import MATCH, SOURCE, BASE, setup, options, until
from app.asr import BYTES_PER_SECOND
from app.audio_capture import CaptureError


def test_distribution_keeps_whole_run_totals_and_histogram_intervals():
    distribution = DelayDistribution()
    assert distribution.snapshot()['p95_interval'] is None
    for value in (.05, .2, .8, 7., 140.):
        distribution.add(value)
    view = distribution.snapshot()
    assert view['samples'] == 5
    assert view['mean_seconds'] == pytest.approx(148.05/5)
    assert view['p50_interval'] == {'lower_seconds': .5, 'upper_seconds': 1.}
    assert view['p95_interval'] == {'lower_seconds': 120., 'upper_seconds': None}
    for value in (math.inf, math.nan, -1):
        with pytest.raises(ValueError):
            distribution.add(value)


def test_two_hour_run_preserves_counters_with_bounded_receipts_and_idempotent_acks():
    clock = [0.]
    metrics = CaptureMetrics(clock=lambda: clock[0])
    for sequence in range(720):
        captured = sequence*10.
        clock[0] = captured+2
        metrics.observe(sequence, captured_tick=captured, phase='in_play',
            named_actions=sequence % 2 == 0, partial_region=False, full_ball=False)
        clock[0] += .5
        assert metrics.acknowledge_render(metrics.epoch, sequence)
        assert not metrics.acknowledge_render(metrics.epoch, sequence)
    metrics.finish()
    clock[0] += 100
    view = metrics.snapshot()
    assert view['elapsed_seconds'] == 7192.5
    assert view['text_windows'] == view['pcm_to_text']['samples'] == 720
    assert view['windows_with_named_actions'] == 360
    assert view['pcm_to_text']['maximum_seconds'] == 2
    assert view['pcm_to_first_render_ack']['maximum_seconds'] == 2.5
    assert view['render_receipts_retained'] == 512
    assert view['phase_changes'] == 0
    assert view['accuracy_metrics'] is None
    assert view['broadcast_to_browser_latency_seconds'] is None
    assert not metrics.acknowledge_render(metrics.epoch, 0)
    assert not metrics.acknowledge_render('a'*32, 719)


def test_missing_capture_or_sequence_does_not_create_latency_sample_or_fake_audio_loss():
    metrics = CaptureMetrics(clock=lambda: 10.)
    for sequence, phase in [(0, 'pre_game'), (3, 'in_play')]:
        metrics.observe(sequence, captured_tick=None, phase=phase, named_actions=False,
            partial_region=False, full_ball=False)
    report = metrics.snapshot()
    assert report['sequence_gaps'] == 2 and report['sequence_gaps_are_not_proven_audio_loss']
    assert report['pcm_to_text']['samples'] == 0 and report['phase_changes'] == 1
    assert not metrics.acknowledge_render(metrics.epoch, 3)
    with pytest.raises(ValueError):
        metrics.observe(3, captured_tick=None, phase='in_play', named_actions=False,
            partial_region=False, full_ball=False)


def test_report_render_receipt_restart_and_no_match_writes(tmp_path):
    async def runner(url, match, **kwargs):
        kwargs['on_pcm'](12*BYTES_PER_SECOND)
        for seq, text in enumerate(['Começou o jogo', 'Azul com a bola no meio-campo pela direita']):
            await kwargs['on_observation']({'source_id': SOURCE['id'], 'sequence': seq,
                'start_seconds': seq*6, 'end_seconds': seq*6+6, 'text': text})
        await asyncio.Event().wait()

    with TestClient(create_app(tmp_path/'metrics.sqlite3', capture_runner=runner)) as client:
        setup(client)
        before = client.get(BASE+'/state').json()
        assert client.get(BASE+'/capture/report').json()['streams'] == []
        assert client.post(BASE+'/capture/start', json=options()).status_code == 202
        deadline = time.monotonic()+3
        while client.get(BASE+'/capture').json()['observations'] != 2:
            assert time.monotonic() < deadline
            time.sleep(.01)
        preview = client.get(BASE+'/live/preview').json()
        payload = {'source_id': SOURCE['id'], 'epoch': preview['capture_epoch'], 'sequence': 1}
        assert client.post(BASE+'/capture/render-ack', json=payload).json() == {'accepted': True}
        assert client.post(BASE+'/capture/render-ack', json=payload).json() == {'accepted': False}
        report = client.get(BASE+'/capture/report').json()
        metrics = report['streams'][0]['metrics']
        assert metrics['text_windows'] == metrics['pcm_to_text']['samples'] == 2
        assert metrics['pcm_to_first_render_ack']['samples'] == 1
        serialized = json.dumps(report)
        assert 'Azul com a bola' not in serialized and 'https://' not in serialized
        assert client.get(BASE+'/state').json() == before
        client.post(BASE+'/capture/stop'); until(client, 'stopped')
        assert client.get(BASE+'/capture/report').json()['streams'][0]['metrics']['text_windows'] == 2
        assert client.post(BASE+'/capture/start', json=options()).status_code == 202
        until(client, 'running')
        assert client.post(BASE+'/capture/render-ack', json=payload).json() == {'accepted': False}
        for invalid in ({**payload, 'sequence': True}, {**payload, 'epoch': 'bad'}, {**payload, 'extra': 1}):
            assert client.post(BASE+'/capture/render-ack', json=invalid).status_code == 422
        assert client.get('/api/matches/missing/capture/report').status_code == 404
        assert client.get(BASE+'/state').json() == before


@pytest.mark.parametrize('error', [WebSocketDisconnect(code=1006), RuntimeError('closed'), OSError('disconnected')])
def test_disconnection_during_initial_websocket_snapshot_releases_subscription(tmp_path, error):
    app = create_app(tmp_path/'disconnect.sqlite3')
    class Socket:
        async def accept(self):
            pass
        async def send_json(self, message):
            raise error

    with TestClient(app) as client:
        setup(client)
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, 'path', None) == '/ws/matches/{match_id}/transcripts')
        async def run():
            for _ in range(50):
                await endpoint(MATCH['id'], Socket())
                assert app.state.transcript_feed._subscribers == {}
        asyncio.run(run())


def test_processed_empty_windows_are_counted_without_fabricating_text_or_delays():
    metrics = CaptureMetrics(clock=lambda: 0.)
    metrics.processed(0, 12, has_new_text=False)
    metrics.processed(1, 22, has_new_text=True)
    view = metrics.snapshot()
    assert view['processed_audio_windows'] == 2 and view['last_processed_audio_end_seconds'] == 22
    assert view['windows_without_new_text'] == 1 and view['text_windows'] == 0
    assert view['pcm_to_text']['samples'] == 0
    with pytest.raises(ValueError):
        metrics.processed(1, 22, has_new_text=False)


def test_immediate_source_end_preserves_final_phase_without_a_polling_race_or_match_write(tmp_path):
    async def runner(url, match, **kwargs):
        kwargs['on_pcm'](18*BYTES_PER_SECOND)
        for seq, text in enumerate(['Começou o jogo', 'Azul com a bola',
                                  'O árbitro apitou o final do jogo']):
            await kwargs['on_observation']({'source_id': SOURCE['id'], 'sequence': seq,
                'start_seconds': seq*6, 'end_seconds': seq*6+6, 'text': text})
    with TestClient(create_app(tmp_path/'eof.sqlite3', capture_runner=runner)) as client:
        setup(client)
        before = client.get(BASE+'/state').json()
        assert client.post(BASE+'/capture/start', json=options()).status_code == 202
        until(client, 'finished')
        assert client.get(BASE+'/live/preview').json() is None
        assert client.get(BASE+'/capture').json()['last_detected_phase'] == 'finished'
        assert client.get(BASE+'/state').json() == before


def test_restarted_failed_sources_keep_failure_counts_and_bounded_attempt_history(tmp_path):
    async def runner(url, match, **kwargs):
        if kwargs['source_id'] == 'failed-source':
            raise CaptureError('upstream_http_403 private')
        kwargs['on_pcm'](6*BYTES_PER_SECOND)
        await kwargs['on_observation']({'source_id': SOURCE['id'], 'sequence': 0,
            'start_seconds': 0, 'end_seconds': 6, 'text': 'Começou o jogo'})
        await asyncio.Event().wait()
    with TestClient(create_app(tmp_path/'failures.sqlite3', capture_runner=runner)) as client:
        setup(client)
        client.put(BASE+'/sources', json=[SOURCE, {**SOURCE, 'id': 'failed-source'}])
        assert client.post(BASE+'/capture/start', json=options()).status_code == 202
        until(client, 'running')
        for count in range(70):
            assert client.post(BASE+'/capture/add', json={'source_id': 'failed-source',
                'permission_confirmed': True}).status_code == 202
            deadline = time.monotonic()+3
            while True:
                report = client.get(BASE+'/capture/report').json()
                if report['completed_attempts_total'] == count+1:
                    break
                assert time.monotonic() < deadline
                time.sleep(.001)
        assert report['failures_by_code'] == {'upstream_http_403': 70}
        assert len(report['recent_completed_attempts']) == 64
        assert client.get(BASE+'/capture').json()['state'] == 'running'
        assert 'private' not in str(report)
