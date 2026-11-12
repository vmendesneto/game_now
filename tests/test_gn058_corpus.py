"""GN-058 synthetic-only corpus metadata tests (no real recordings)."""
from copy import deepcopy
import json

import pytest

from scripts import gn058_corpus as corpus


def fixture():
    manifest = {
        "schema_version": 1,
        "dataset_id": "corpus-original",
        "rights_statement": "User-created synthetic speech with explicit permission for tests",
        "independent_human_annotation": True,
        "recordings": [
            {"group_id": "rec-01", "source_ids": ["radio-01", "yt-01"], "duration_seconds": 50,
             "content_sha256": "1" * 64, "split": "train"},
            {"group_id": "rec-02", "source_ids": ["radio-02"], "duration_seconds": 100,
             "content_sha256": "2" * 64, "split": "test"},
        ],
    }
    rows = [
        {"group_id": "rec-01", "source_id": "radio-01", "start_seconds": 0,
         "end_seconds": 6, "team_id": "team-azul", "zone": {"band": 3, "lane": "center"},
         "reference_text": "texto privado da amostra"},
        {"group_id": "rec-01", "source_id": "yt-01", "start_seconds": 6,
         "end_seconds": 12, "narration_kind": "ad", "event_kind": None},
        {"group_id": "rec-02", "source_id": "radio-02", "start_seconds": 0,
         "end_seconds": 10, "event_kind": "goal", "player_id": None},
    ]
    return manifest, rows


def test_metadata_summary_does_not_export_text_or_labels():
    manifest, rows = fixture()
    before = deepcopy((manifest, rows))
    result = corpus.report(manifest, rows, manifest_sha="a" * 64, annotations_sha="b" * 64)
    assert result["annotation_segments"] == 3
    assert result["segments_by_split"] == {"train": 2, "validation": 0, "test": 1}
    assert result["annotated_fields"]["event_kind"] == 2
    serialized = json.dumps(result)
    assert "texto privado" not in serialized and "team-azul" not in serialized
    assert "radio-01" not in serialized and "yt-01" not in serialized
    assert (manifest, rows) == before


def test_duplicate_fingerprint_across_splits_rejected():
    m, r = fixture()
    m["recordings"][1]["content_sha256"] = "1" * 64
    with pytest.raises(corpus.CorpusError, match="across splits"):
        corpus.report(m, r, manifest_sha="x", annotations_sha="y")


@pytest.mark.parametrize("change", [
    lambda m, r: m.update({"independent_human_annotation": False}),
    lambda m, r: m.update({"rights_statement": "unknown"}),
    lambda m, r: m["recordings"][0].update({"duration_seconds": float("nan")}),
    lambda m, r: m["recordings"][0].update({"source_ids": ["radio-01", "radio-01"]}),
    lambda m, r: r[0].update({"source_id": "other-03"}),
    lambda m, r: r[0].update({"end_seconds": 51}),
    lambda m, r: r[0].update({"zone": {"band": 6, "lane": "center"}}),
    lambda m, r: r[0].update({"team_id": 123}),
    lambda m, r: r[1].update({"narration_kind": "invented"}),
    lambda m, r: r[1].update({"event_kind": "invented"}),
    lambda m, r: r[1].update({"start_seconds": True}),
    lambda m, r: r.append(deepcopy(r[0])),
    lambda m, r: r.pop(1),
    lambda m, r: r[0].update({"invented_field": "sensitive"}),
])
def test_invalid_corpus_refused(change):
    m, r = fixture()
    change(m, r)
    with pytest.raises(corpus.CorpusError):
        corpus.report(m, r, manifest_sha="x", annotations_sha="y")


def test_json_duplicate_keys_refused(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"schema_version":1,"schema_version":2}')
    with pytest.raises(corpus.CorpusError, match="Duplicate"):
        corpus._read_json(p)


def test_cli_requires_permission_and_never_overwrites_report(tmp_path, capsys):
    m, r = fixture()
    mp, ap, op = (tmp_path / x for x in ("manifest.json", "labels.json", "result.json"))
    mp.write_text(json.dumps(m))
    ap.write_text(json.dumps(r))
    args = ["--manifest", str(mp), "--annotations", str(ap), "--output", str(op)]
    assert corpus.main(args) == 2
    assert not op.exists()
    assert corpus.main(args + ["--permission-confirmed"]) == 0
    result = json.loads(op.read_text())
    assert result["audio_or_text_exported"] is False
    op.write_text("original contents")
    assert corpus.main(args + ["--permission-confirmed"]) == 2
    assert op.read_text() == "original contents"
    assert "texto privado" not in capsys.readouterr().out


def test_boolean_time_and_empty_labels_rejected():
    m, r = fixture()
    del r[0]["team_id"]
    del r[0]["zone"]
    with pytest.raises(corpus.CorpusError, match="no explicit labels"):
        corpus.report(m, r, manifest_sha="x", annotations_sha="y")
