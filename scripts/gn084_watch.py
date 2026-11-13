"""Observe an existing local capture without starting, stopping or reading media."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import quote, urlsplit
from urllib.request import ProxyHandler, build_opener


def _read(url: str) -> dict | None:
    with build_opener(ProxyHandler({})).open(url, timeout=4) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Operational response exceeds size limit')
    return json.loads(raw)


def collect(base: str, match_id: str, *, seconds: float = 600, interval: float = 2,
            reader=_read, clock=time.monotonic, sleep=time.sleep,
            include_transcript_tail: bool = False, stop_when_capture_ends: bool = False) -> dict:
    location = urlsplit(base)
    if (location.scheme != 'http' or location.hostname not in ('127.0.0.1', '::1')
            or location.username or location.password or location.path not in ('', '/')
            or location.query or location.fragment):
        raise ValueError('Use a loopback HTTP server without credentials or paths')
    if not 1 <= seconds <= 10800 or not .1 <= interval <= 60:
        raise ValueError('Invalid observation duration or interval')
    api = base.rstrip('/')+'/api/matches/'+quote(match_id, safe='')
    started = clock()
    utc_start = datetime.now(timezone.utc).isoformat()
    samples = errors = 0
    maximum_health = None
    report = None
    phases = []
    failures = []
    previous_errors = {}
    transcript_tail = None
    consecutive_errors = 0
    ended_without_terminal_state = False
    while True:
        try:
            health_started = clock()
            health = reader(base.rstrip('/')+'/health')
            health_delay = max(0., clock()-health_started)
            maximum_health = max(maximum_health or 0., health_delay)
            if not isinstance(health, dict):
                raise ValueError('Invalid health response')
            current = reader(api+'/capture/report')
            if not isinstance(current, dict) or current.get('kind') != 'operational_capture_report':
                raise ValueError('Invalid operational report')
            report = current
            if include_transcript_tail:
                snapshot = reader(api+'/transcripts?limit=100')
                if isinstance(snapshot, dict):
                    transcript_tail = snapshot
            preview = reader(api+'/live/preview')
            if preview and (not phases or phases[-1]['phase'] != preview['phase']):
                phases.append({'phase': preview['phase'], 'audio_seconds': preview['last_audio_seconds'],
                               'observed_elapsed_seconds': max(0., clock()-started)})
            for stream in report['streams']:
                error = stream['error_code'] if stream['state'] == 'error' else None
                if error and previous_errors.get(stream['source_id']) != error:
                    failures.append({'source_id': stream['source_id'], 'error_code': error,
                                     'observed_elapsed_seconds': max(0., clock()-started)})
                    failures = failures[-200:]
                previous_errors[stream['source_id']] = error
            samples += 1
            consecutive_errors = 0
            if stop_when_capture_ends and report['streams'] and all(
                    stream['state'] in ('finished', 'stopped', 'error') for stream in report['streams']):
                break
        except (OSError, ValueError, KeyError, TypeError):
            errors += 1
            consecutive_errors += 1
            if stop_when_capture_ends and consecutive_errors >= 3:
                ended_without_terminal_state = True
                break
        remaining = seconds - (clock()-started)
        if remaining <= 0:
            break
        sleep(min(interval, remaining))
    expected = ['pre_game', 'in_play', 'half_time', 'second_half', 'finished']
    seen = [item['phase'] for item in phases]
    cursor = 0
    for phase in seen:
        if cursor < len(expected) and phase == expected[cursor]:
            cursor += 1
    return {'task': 'GN-084', 'kind': 'operational_observation',
            'started_at': utc_start, 'finished_at': datetime.now(timezone.utc).isoformat(),
            'observed_seconds': max(0., clock()-started), 'successful_polls': samples,
            'request_errors': errors, 'maximum_health_response_seconds': maximum_health,
            'phase_changes': phases, 'technical_phase_cycle_observed': cursor == len(expected),
            'recent_source_failures': failures, 'latest_capture_report': report,
            'audio_or_transcripts_saved': include_transcript_tail,
            'audio_saved': False, 'transcript_tail': transcript_tail,
            'ended_without_terminal_state': ended_without_terminal_state,
            'capture_lifecycle_changed': False,
            'independent_accuracy_metrics': None,
            'broadcast_to_browser_latency_seconds': None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--match-id', required=True)
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-transcript-tail', action='store_true',
                        help='Opt-in private text tail for failure diagnosis; never includes audio')
    parser.add_argument('--until-capture-ends', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError('Choose a new output file; existing reports are preserved')
        result = collect(args.base_url, args.match_id, seconds=args.seconds, interval=args.interval,
                         include_transcript_tail=args.include_transcript_tail,
                         stop_when_capture_ends=args.until_capture_ends)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(json.dumps({'output': str(args.output), 'polls': result['successful_polls'],
                          'request_errors': result['request_errors']}))
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
