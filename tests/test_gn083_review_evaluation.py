"""Synthetic labels test the comparison machinery, not real-world precision."""
from copy import deepcopy

import pytest

from scripts.evaluate_gn083_review import assess
from tests.test_capture_runtime import MATCH, SOURCE


def inputs():
    archive = {'match_id': MATCH['id'], 'match': MATCH, 'windows': [
        {'source_id': SOURCE['id'], 'sequence': seq, 'audio_start_seconds': seq*10,
         'audio_end_seconds': (seq+1)*10, 'requested_video_start_seconds': 575+seq*10,
         'text': 'Azul com a bola no meio-campo pela direita'} for seq in range(30)]}
    reference = [{'source_id': SOURCE['id'], 'start_seconds': seq*10, 'end_seconds': (seq+1)*10,
                  'team_id': MATCH['home']['id'], 'player_id': None,
                  'zone': {'band': 3, 'lane': 'right'}} for seq in range(30)]
    declaration = {'match_id': MATCH['id'], 'source_id': SOURCE['id'],
        'requested_media_start_seconds': 575, 'duration_seconds': 300,
        'independent_human_annotation': True, 'predictions_supplied': False,
        'reviewer': 'synthetic-test-only', 'annotated_segments': 30}
    return archive, reference, declaration


def test_comparison_records_scope_and_does_not_export_content_or_certify_independence():
    archive, reference, declaration = inputs()
    original = deepcopy(archive)
    report = assess(archive, reference, declaration)
    assert report['duration_requirement_met']
    assert report['reviewed_seconds_by_field'] == {'team_id': 300, 'player_id': 300, 'zone': 300}
    assert report['comparison']['metrics']['team_id']['correct'] == 30
    assert report['human_independence'] == 'declared_not_certified'
    assert report['live_ui_sequence_accuracy_measured'] is False
    assert not report['audio_or_transcripts_exported'] and not report['state_updated']
    assert 'Azul com a bola' not in str(report)
    assert archive == original


def test_declared_duration_does_not_substitute_for_reviewed_field_coverage():
    archive, reference, declaration = inputs()
    for row in reference:
        del row['zone']
    report = assess(archive, reference, declaration)
    assert not report['duration_requirement_met']
    assert report['reviewed_seconds_by_field']['zone'] == 0


@pytest.mark.parametrize('change', [
    {'independent_human_annotation': False}, {'predictions_supplied': True},
    {'reviewer': ''}, {'match_id': 'wrong-match'}, {'requested_media_start_seconds': 530},
    {'annotated_segments': 29},
])
def test_review_requires_matching_independent_declaration(change):
    archive, reference, declaration = inputs()
    with pytest.raises(ValueError):
        assess(archive, reference, {**declaration, **change})


def test_duplicated_or_unknown_labels_cannot_create_favorable_metrics():
    archive, reference, declaration = inputs()
    reference[1] = deepcopy(reference[0])
    with pytest.raises(ValueError, match='Duplicate'):
        assess(archive, reference, declaration)
    archive, reference, declaration = inputs()
    reference[0]['team_id'] = 'unknown-team'
    with pytest.raises(ValueError, match='team label'):
        assess(archive, reference, declaration)
