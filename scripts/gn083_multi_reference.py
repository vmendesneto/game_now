"""Compare sets of textual labels; never infer touch times or possession order."""
from __future__ import annotations

from app.contracts import Match
from app.gn083_offline import analyze_observations
from app.narration_tracking import track_narration

FIELDS = ('team_ids', 'player_ids', 'zones')


def _zone(value) -> tuple[int, str]:
    if (not isinstance(value, dict) or set(value) != {'band', 'lane'}
            or type(value['band']) is not int or not 1 <= value['band'] <= 5
            or value['lane'] not in ('left', 'center', 'right')):
        raise ValueError('Invalid human reference zone')
    return value['band'], value['lane']


def validate_reference(match: Match, reference: list[dict]) -> None:
    allowed = {'team_ids': {match.home.id, match.away.id},
               'player_ids': {player.id for player in match.players}}
    previous_end = -1.
    for row in sorted(reference, key=lambda item: item['start_seconds']):
        if not previous_end <= row['start_seconds'] < row['end_seconds']:
            raise ValueError('Multi-label review intervals must be positive and nonoverlapping')
        previous_end = row['end_seconds']
        if any(field in row for field in ('team_id', 'player_id', 'zone')):
            raise ValueError('Use plural label arrays for annotation schema v2')
        for field in FIELDS:
            if field not in row:
                continue
            values = row[field]
            if not isinstance(values, list) or len(values) > 256:
                raise ValueError('Multi-label fields must be arrays; empty means reviewed negative')
            normalized = [_zone(item) for item in values] if field == 'zones' else values
            if field != 'zones' and any(not isinstance(item, str) or item not in allowed[field] for item in values):
                raise ValueError('Human label is outside the archived match roster')
            if len(set(normalized)) != len(normalized):
                raise ValueError('Repeat labels are not separate touches in a set reference')


def evaluate_multi(match: Match, observations: list[dict], reference: list[dict]) -> dict:
    validate_reference(match, reference)
    predictions = analyze_observations(match, observations, include_text=False)
    for prediction, observation in zip(predictions, observations, strict=True):
        actions = track_narration(match, observation['text'])
        prediction['team_ids'] = {item['team_id'] for item in actions if item['team_id']}
        prediction['player_ids'] = {item['player_id'] for item in actions if item['player_id']}
        prediction['zones'] = {(item['region']['bands'][0], item['region']['lane']) for item in actions
            if item['region'] and len(item['region']['bands']) == 1
            and item['region']['lane'] in ('left', 'center', 'right')}
        for singular, plural in (('team_id', 'team_ids'), ('player_id', 'player_ids')):
            if prediction.get(singular):
                prediction[plural].add(prediction[singular])
        if prediction.get('zone'):
            prediction['zones'].add(_zone(prediction['zone']))
    # Match solely by source and interval geometry, never by a favorable label.
    candidates = []
    for i, gold in enumerate(reference):
        for j, pred in enumerate(predictions):
            if gold['source_id'] != pred['source_id']:
                continue
            gap = max(0., max(gold['start_seconds'], pred['start_seconds'])
                      - min(gold['end_seconds'], pred['end_seconds']))
            if gap <= 2:
                midpoint = abs((gold['start_seconds']+gold['end_seconds'])/2
                               - (pred['start_seconds']+pred['end_seconds'])/2)
                candidates.append((midpoint, gap, i, j))
    assigned, used = {}, set()
    for _, _, i, j in sorted(candidates):
        if i not in assigned and j not in used:
            assigned[i] = predictions[j]
            used.add(j)
    metrics = {}
    for field in FIELDS:
        annotated = support = predicted = correct = fp = fn = exact = covered = 0
        for i, gold in enumerate(reference):
            if field not in gold:
                continue
            annotated += 1
            actual = {_zone(value) for value in gold[field]} if field == 'zones' else set(gold[field])
            found = assigned.get(i, {}).get(field, set())
            support += len(actual)
            predicted += len(found)
            correct += len(actual & found)
            fp += len(found-actual)
            fn += len(actual-found)
            exact += actual == found
            covered += bool(found)
        metrics[field] = {'annotated_intervals': annotated, 'reference_positives': support,
            'predicted_positives': predicted, 'correct': correct, 'false_positives': fp,
            'false_negatives': fn, 'precision': round(correct/(correct+fp), 4) if correct+fp else None,
            'recall': round(correct/support, 4) if support else None,
            'coverage': round(covered/annotated, 4) if annotated else None,
            'exact_set_agreement': round(exact/annotated, 4) if annotated else None}
    return {'evidence': 'multi_label_reference_comparison', 'reference_segments': len(reference),
        'aligned_segments': len(assigned), 'unmatched_reference': len(reference)-len(assigned),
        'unmatched_predictions': len(predictions)-len(used), 'metrics': metrics,
        'matching': 'one_to_one_by_time_midpoint_with_2s_gap_tolerance',
        'prediction_basis': 'window_analysis_plus_named_action_annotations',
        'warning': 'Approximate window matching; labels are unique per interval, not verified touches',
        'touch_count_measured': False, 'action_order_accuracy_measured': False,
        'possession_transitions_measured': False, 'team_zone_association_measured': False,
        'live_ui_sequence_accuracy_measured': False, 'word_error_rate': None}
