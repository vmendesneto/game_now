"""Compare retained real text with separately declared human reference labels."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.contracts import Match
from app.gn083_offline import analyze_observations, evaluate
from scripts.gn083_multi_reference import evaluate_multi


def _read(path: Path):
    if not path.is_file() or path.stat().st_size > 8_000_000:
        raise ValueError('Review input missing or too large')
    return json.loads(path.read_text(encoding='utf-8'))


def assess(archive: dict, reference: list, declaration: dict) -> dict:
    if not isinstance(archive, dict) or not isinstance(declaration, dict):
        raise ValueError('Archive and declaration must be objects')
    if (declaration.get('independent_human_annotation') is not True
            or declaration.get('predictions_supplied') is not False
            or not isinstance(declaration.get('reviewer'), str) or not declaration['reviewer'].strip()):
        raise ValueError('An independent human review declaration is required')
    if declaration.get('match_id') != archive.get('match_id'):
        raise ValueError('Review and text archive identify different matches')
    source = declaration.get('source_id')
    start = declaration.get('requested_media_start_seconds')
    duration = declaration.get('duration_seconds')
    if (not isinstance(source, str) or type(start) not in (int, float) or not 0 <= start <= 86400
            or type(duration) not in (int, float) or not 5 <= duration <= 600):
        raise ValueError('Invalid declared recording interval')
    if not isinstance(reference, list) or not 1 <= len(reference) <= 3000:
        raise ValueError('Human labels must be a nonempty array')
    if declaration.get('annotated_segments') != len(reference):
        raise ValueError('Declaration and exported annotations do not agree')
    match = Match.model_validate(archive['match'])
    players = {player.id for player in match.players}
    teams = {match.home.id, match.away.id}
    seen = set()
    for row in reference:
        if not isinstance(row, dict):
            raise ValueError('Reference interval must be an object')
        if (row.get('source_id') != source or type(row.get('start_seconds')) not in (int, float)
                or type(row.get('end_seconds')) not in (int, float)
                or not 0 <= row['start_seconds'] <= row['end_seconds'] <= duration):
            raise ValueError('Reference labels must use the declared source and relative interval')
        key = row['start_seconds'], row['end_seconds']
        if key in seen:
            raise ValueError('Duplicate human reference interval')
        seen.add(key)
        if row.get('player_id') is not None and row['player_id'] not in players:
            raise ValueError('Human player label is not in the archived roster')
        if row.get('team_id') is not None and row['team_id'] not in teams:
            raise ValueError('Human team label is not in the archived match')
    observations = []
    for row in archive['windows']:
        if row['source_id'] != source:
            continue
        offset = row.get('requested_video_start_seconds')
        if offset is None or abs(offset-row['audio_start_seconds']-start) > .001:
            raise ValueError('Retained text uses a different or unknown recording offset')
        if row['audio_end_seconds'] > duration:
            continue
        observations.append({'source_id': source, 'sequence': row['sequence'],
            'start_seconds': row['audio_start_seconds'], 'end_seconds': row['audio_end_seconds'], 'text': row['text']})
    observations.sort(key=lambda row: row['sequence'])
    if not observations:
        raise ValueError('No retained text for the reviewed interval')
    version = declaration.get('annotation_schema_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported human annotation schema')
    if version == 2:
        if declaration.get('review_unit') != 'unique_labels_per_interval':
            raise ValueError('Multi-label annotation must declare its review unit')
        result = evaluate_multi(match, observations, reference)
        fields = ('team_ids', 'player_ids', 'zones')
    else:
        predictions = analyze_observations(match, observations, include_text=True)
        result = evaluate(predictions, reference)
        fields = ('team_id', 'player_id', 'zone')
    def covered(field):
        intervals = sorted((row['start_seconds'], row['end_seconds']) for row in reference if field in row)
        total = 0.
        end = -1.
        for start_at, end_at in intervals:
            total += max(0., end_at-max(start_at, end))
            end = max(end, end_at)
        return total
    coverage = {field: covered(field) for field in fields}
    return {'task': 'GN-083', 'kind': 'declared_independent_human_comparison',
            'match_id': match.id, 'source_id': source,
            'requested_media_start_seconds': start, 'duration_seconds': duration,
            'reviewer': declaration['reviewer'], 'human_independence': 'declared_not_certified',
            'media_offset_verified_by_annotator': declaration.get('media_start_verified_by_annotator') is True,
            'extracted_media_seek_independently_verified': False,
            'annotation_schema_version': version,
            'evaluation_target': ('unique_textual_labels_per_review_interval' if version == 2
                                  else 'window_level_interpretation_of_saved_real_asr'),
            'live_ui_sequence_accuracy_measured': False,
            'reviewed_seconds_by_field': coverage,
            'duration_requirement_met': duration >= 300 and min(coverage.values()) >= 300,
            'comparison': result, 'audio_or_transcripts_exported': False,
            'state_updated': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError('Existing result is preserved; choose a new output')
        result = assess(_read(args.archive), _read(args.reference), _read(args.declaration))
        result['reference_sha256'] = sha256(args.reference.read_bytes()).hexdigest()
        result['declaration_sha256'] = sha256(args.declaration.read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(2, str(exc)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
