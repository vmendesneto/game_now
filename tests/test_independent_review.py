"""Review material must not prefill, leak or certify automatic predictions."""
import json
import re

import pytest

from app.configuration import MatchConfig
from app.contracts import AudioSource
from app.storage import SQLiteStore
from scripts.prepare_gn083_review import prepare
from tests.test_capture_runtime import MATCH, SOURCE


def test_preparation_is_readonly_blind_and_preserves_json_without_script_injection(tmp_path):
    store = SQLiteStore(tmp_path/'source.sqlite3')
    match = {**MATCH, 'home': {**MATCH['home'], 'name': '</script><img src=x>'}}
    store.create_match(MatchConfig.model_validate(match))
    store.replace_sources(MATCH['id'], [AudioSource.model_validate(SOURCE)])
    before = store.path.read_bytes()
    output = prepare(store.path, MATCH['id'], SOURCE['id'], tmp_path/'review')
    page = output.read_text(encoding='utf-8')
    embedded = re.search(r'<script id="review-data" type="application/json">(.*?)</script>', page).group(1)
    assert json.loads(embedded)['match']['home']['name'] == '</script><img src=x>'
    assert '<img src=x>' not in embedded
    assert store.path.read_bytes() == before
    assert all(tag not in page for tag in ('<audio', '<video', '<iframe'))
    assert 'raw_text' not in page and 'transcripts' not in page
    assert 'independent_human_annotation:true' in page
    with pytest.raises(ValueError, match='never overwritten'):
        prepare(store.path, MATCH['id'], SOURCE['id'], output.parent)
    store.path.unlink()  # Windows rejects this if the read connection remains open.
    assert not store.path.exists() and output.is_file()


@pytest.mark.parametrize('start,duration', [(-1, 300), (575, 601), (575, 0)])
def test_review_rejects_invalid_intervals(tmp_path, start, duration):
    with pytest.raises(ValueError, match='interval'):
        prepare(tmp_path/'missing.sqlite3', MATCH['id'], SOURCE['id'], tmp_path/'review',
                start_seconds=start, duration_seconds=duration)
