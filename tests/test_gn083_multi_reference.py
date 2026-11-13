"""Synthetic multi-label ground truth tests; no human annotation claimed."""
from copy import deepcopy

import pytest

from scripts.evaluate_gn083_review import assess
from tests.test_narration_tracking import game


def inputs(text='Caio recebeu no meio-campo pela esquerda. Serve Davi. Beto recuperou no meio-campo pela direita.'):
    match = game()
    archive = {'match_id': match.id, 'match': match.model_dump(mode='json'), 'windows': [
        {'source_id': 'source-multi', 'sequence': seq, 'audio_start_seconds': seq*10,
         'audio_end_seconds': seq*10+10, 'requested_video_start_seconds': 575+seq*10,
         'text': text} for seq in range(30)]}
    reference = [{'source_id': 'source-multi', 'start_seconds': seq*10, 'end_seconds': seq*10+10,
                  'team_ids': ['blue', 'red'], 'player_ids': ['caio', 'davi', 'beto'],
                  'zones': [{'band': 3, 'lane': 'left'}, {'band': 3, 'lane': 'right'}]} for seq in range(30)]
    declaration = {'annotation_schema_version': 2, 'review_unit': 'unique_labels_per_interval',
        'match_id': match.id, 'source_id': 'source-multi', 'requested_media_start_seconds': 575,
        'duration_seconds': 300, 'independent_human_annotation': True,
        'predictions_supplied': False, 'reviewer': 'synthetic-only', 'annotated_segments': 30}
    return archive, reference, declaration


def test_several_players_teams_and_regions_can_be_correct_in_the_same_interval():
    values = inputs()
    before = deepcopy(values)
    report = assess(*values)
    assert values == before
    assert report['duration_requirement_met']
    assert report['evaluation_target'] == 'unique_textual_labels_per_review_interval'
    metrics = report['comparison']['metrics']
    assert metrics['team_ids']['correct'] == 60
    assert metrics['player_ids']['correct'] == 90
    assert metrics['zones']['correct'] == 60
    assert metrics['player_ids']['precision'] == metrics['player_ids']['recall'] == 1
    assert not report['comparison']['touch_count_measured']
    assert not report['comparison']['possession_transitions_measured']


def test_extra_predicted_player_is_a_false_positive_instead_of_a_favorable_single_choice():
    archive, reference, declaration = inputs()
    for row in reference:
        row['player_ids'].remove('beto')
    metric = assess(archive, reference, declaration)['comparison']['metrics']['player_ids']
    assert metric['correct'] == 60 and metric['false_positives'] == 30
    assert metric['precision'] == .6667 and metric['recall'] == 1
    assert metric['exact_set_agreement'] == 0


def test_repeated_player_is_one_identification_and_not_two_measured_touches():
    archive, reference, declaration = inputs('Caio recebeu. Caio recebe.')
    for row in reference:
        row['player_ids'] = ['caio']
    metric = assess(archive, reference, declaration)['comparison']['metrics']['player_ids']
    assert metric['correct'] == metric['predicted_positives'] == 30


def test_unreviewed_fields_and_empty_reviewed_sets_are_different():
    archive, reference, declaration = inputs()
    for row in reference:
        row['player_ids'] = []
        del row['zones']
    report = assess(archive, reference, declaration)
    assert report['reviewed_seconds_by_field']['player_ids'] == 300
    assert report['reviewed_seconds_by_field']['zones'] == 0
    assert not report['duration_requirement_met']
    metric = report['comparison']['metrics']['player_ids']
    assert metric['reference_positives'] == 0 and metric['false_positives'] == 90


@pytest.mark.parametrize('field,value', [('player_ids', ['caio', 'caio']),
    ('player_ids', ['missing']), ('player_ids', None), ('team_ids', ['missing']),
    ('zones', [{'band': 6, 'lane': 'left'}]), ('zones', [None])])
def test_invalid_or_repeated_label_sets_are_rejected(field, value):
    archive, reference, declaration = inputs()
    reference[0][field] = value
    with pytest.raises(ValueError):
        assess(archive, reference, declaration)


def test_overlap_or_stale_single_label_export_cannot_create_multi_label_metrics():
    archive, reference, declaration = inputs()
    reference[1]['start_seconds'] = 5
    with pytest.raises(ValueError, match='nonoverlapping'):
        assess(archive, reference, declaration)
    archive, reference, declaration = inputs()
    reference[0]['player_id'] = 'caio'
    with pytest.raises(ValueError, match='plural'):
        assess(archive, reference, declaration)


def test_matching_uses_time_instead_of_finding_favorable_player_labels():
    archive, reference, declaration = inputs('Caio recebeu.')
    archive['windows'][1]['text'] = 'Beto recuperou.'
    archive['windows'] = archive['windows'][:2]
    reference = reference[:2]
    reference[0]['player_ids'] = ['beto']
    reference[1]['player_ids'] = ['caio']
    declaration['annotated_segments'] = 2
    metric = assess(archive, reference, declaration)['comparison']['metrics']['player_ids']
    assert metric['correct'] == 0
    assert metric['false_positives'] == metric['false_negatives'] == 2
