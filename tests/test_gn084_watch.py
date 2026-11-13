import pytest

from scripts.gn084_watch import collect


def test_observer_is_readonly_and_reports_phases_failures_and_health_time():
    clock = [0.]
    requested = []
    phases = ['pre_game', 'in_play', 'half_time', 'second_half', 'finished']
    def read(url):
        requested.append(url)
        if url.endswith('/health'):
            clock[0] += .01
            return {'ok': True}
        index = min(int(clock[0]), 4)
        if url.endswith('/capture/report'):
            return {'kind': 'operational_capture_report', 'streams': [{'source_id': 'test-source',
                'state': 'error' if index == 2 else 'running',
                'error_code': 'capture_failed' if index == 2 else None}]}
        return {'phase': phases[index], 'last_audio_seconds': index*1800}
    def sleep(seconds):
        clock[0] += seconds
    report = collect('http://127.0.0.1:8001', 'match-001', seconds=5, interval=1,
                     reader=read, clock=lambda: clock[0], sleep=sleep)
    assert report['technical_phase_cycle_observed']
    assert report['maximum_health_response_seconds'] == pytest.approx(.01)
    assert len(report['recent_source_failures']) == 1
    assert report['request_errors'] == 0
    assert report['broadcast_to_browser_latency_seconds'] is None
    assert all(url.endswith(('/health', '/capture/report', '/live/preview')) for url in requested)
    assert not report['capture_lifecycle_changed'] and not report['audio_or_transcripts_saved']


def test_temporary_server_failure_is_counted_without_inventing_phase_cycle():
    clock = [0.]
    def read(url):
        raise OSError('private server exception')
    def sleep(seconds):
        clock[0] += seconds
    report = collect('http://127.0.0.1:8001', 'match-001', seconds=2, interval=1,
                     reader=read, clock=lambda: clock[0], sleep=sleep)
    assert report['request_errors'] == 3 and not report['technical_phase_cycle_observed']
    assert report['latest_capture_report'] is None
    assert 'private server exception' not in str(report)


@pytest.mark.parametrize('base', ['https://example.org', 'http://localhost:8000',
    'http://127.0.0.1:8000/secret', 'http://user:password@127.0.0.1:8000'])
def test_observer_cannot_be_pointed_at_arbitrary_network_targets(base):
    with pytest.raises(ValueError):
        collect(base, 'match-001')


def test_private_text_tail_is_explicit_and_observer_ends_after_terminal_state():
    calls = []
    def read(url):
        calls.append(url)
        if url.endswith('/health'):
            return {'ok': True}
        if url.endswith('/capture/report'):
            return {'kind': 'operational_capture_report', 'streams': [
                {'source_id': 'test-source', 'state': 'finished', 'error_code': None}]}
        if '/transcripts?' in url:
            return {'entries': [{'text': 'Synthetic private text for export test'}]}
        return {'phase': 'finished', 'last_audio_seconds': 7200}
    report = collect('http://127.0.0.1:8001', 'match-001', seconds=600,
                     reader=read, clock=lambda: 0., sleep=lambda seconds: pytest.fail('Should stop'),
                     include_transcript_tail=True, stop_when_capture_ends=True)
    assert report['successful_polls'] == 1 and report['audio_saved'] is False
    assert report['transcript_tail']['entries'][0]['text'].startswith('Synthetic')
    assert report['audio_or_transcripts_saved'] is True
    assert not report['technical_phase_cycle_observed']
    assert all('/capture/stop' not in url and '/capture/start' not in url for url in calls)
