"""GN-058: validate a rights-declared, human-annotated pt-BR football corpus.

Only local JSON is read. The output is a metadata-only summary, never source
media, text, source URLs, or individual labels. No dataset is bundled here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

from app.contracts import Category, EventKind

MAX_ROWS = 3000
MAX_JSON_BYTES = 2_000_000
MAX_SECONDS = 600
FIELDS = ("team_id", "player_id", "zone", "event_kind", "narration_kind")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
SPLITS = ("train", "validation", "test")


class CorpusError(ValueError):
    """Unsafe, incomplete or inconsistent corpus metadata."""


def _object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise CorpusError("Duplicate JSON object key")
        obj[key] = value
    return obj


def _read_json(path: Path) -> tuple[object, str]:
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise CorpusError("JSON file not found or exceeds size limit")
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs), sha256(raw).hexdigest()
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusError("JSON must be valid UTF-8") from exc


def _id(value: object) -> bool:
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))


def _seconds(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= MAX_SECONDS


def _manifest(value: object) -> tuple[str, dict[str, tuple[dict, str]]]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "dataset_id", "rights_statement", "independent_human_annotation", "recordings"
    }:
        raise CorpusError("Manifest has unexpected or missing fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or not _id(value["dataset_id"]):
        raise CorpusError("Unsupported corpus version or dataset_id")
    if (not isinstance(value["rights_statement"], str)
            or not 12 <= len(value["rights_statement"].strip()) <= 500):
        raise CorpusError("A specific rights statement is mandatory")
    if value["independent_human_annotation"] is not True:
        raise CorpusError("Independent human annotations must be declared")
    recordings = value["recordings"]
    if not isinstance(recordings, list) or not 1 <= len(recordings) <= MAX_ROWS:
        raise CorpusError("Manifest requires a bounded nonempty recordings list")
    by_group = {}
    by_fingerprint = {}
    for item in recordings:
        if not isinstance(item, dict) or set(item) != {
            "group_id", "source_ids", "duration_seconds", "content_sha256", "split"
        }:
            raise CorpusError("Invalid recording group shape")
        group_id, sources = item["group_id"], item["source_ids"]
        if not _id(group_id) or group_id in by_group:
            raise CorpusError("Invalid or duplicate recording group ID")
        if (not isinstance(sources, list) or not sources or len(sources) > 20
                or not all(_id(x) for x in sources) or len(set(sources)) != len(sources)):
            raise CorpusError("Invalid source IDs")
        duration = item["duration_seconds"]
        if not _seconds(duration) or duration == 0:
            raise CorpusError("Invalid recording duration")
        fingerprint, split = item["content_sha256"], item["split"]
        if not isinstance(fingerprint, str) or not FINGERPRINT.fullmatch(fingerprint) or split not in SPLITS:
            raise CorpusError("Invalid recording fingerprint or split")
        if fingerprint in by_fingerprint and by_fingerprint[fingerprint] != split:
            raise CorpusError("Same recording fingerprint occurs across splits")
        by_fingerprint[fingerprint] = split
        by_group[group_id] = (item, split)
    return value["dataset_id"], by_group


def _label(row: dict) -> None:
    allowed = {"group_id", "source_id", "start_seconds", "end_seconds", "reference_text", *FIELDS}
    if set(row) - allowed or not any(key in row for key in FIELDS):
        raise CorpusError("Annotation has unknown keys or no explicit labels")
    for key in ("team_id", "player_id"):
        if key in row and row[key] is not None and not _id(row[key]):
            raise CorpusError("Invalid team/player label ID")
    if "narration_kind" in row and row["narration_kind"] is not None:
        if not isinstance(row["narration_kind"], str) or row["narration_kind"] not in set(Category):
            raise CorpusError("Invalid narration label")
    if "event_kind" in row and row["event_kind"] is not None:
        if not isinstance(row["event_kind"], str) or row["event_kind"] not in set(EventKind):
            raise CorpusError("Invalid event label")
    if "zone" in row and row["zone"] is not None:
        zone = row["zone"]
        if (not isinstance(zone, dict) or set(zone) != {"band", "lane"}
                or type(zone["band"]) is not int or zone["band"] not in range(1, 6)
                or zone["lane"] not in ("left", "center", "right")):
            raise CorpusError("Invalid field zone label")
    if "reference_text" in row:
        txt = row["reference_text"]
        if not isinstance(txt, str) or not 1 <= len(txt.strip()) <= 2048:
            raise CorpusError("Invalid reference text")


def report(manifest: object, annotations: object, *, manifest_sha: str, annotations_sha: str) -> dict:
    dataset_id, groups = _manifest(manifest)
    if not isinstance(annotations, list) or not 1 <= len(annotations) <= MAX_ROWS:
        raise CorpusError("Annotations must be a bounded nonempty JSON array")
    counts = Counter()
    coverage = Counter()
    seen = set()
    seen_sources = set()
    for row in annotations:
        if not isinstance(row, dict) or not _id(row.get("group_id")) or not _id(row.get("source_id")):
            raise CorpusError("Annotation must identify its recording and source")
        group_id, source = row["group_id"], row["source_id"]
        if group_id not in groups:
            raise CorpusError("Annotation references unknown recording group")
        group, split = groups[group_id]
        if source not in group["source_ids"]:
            raise CorpusError("Annotation references unknown source within recording")
        start, end = row.get("start_seconds"), row.get("end_seconds")
        if not _seconds(start) or not _seconds(end) or start > end or end > group["duration_seconds"]:
            raise CorpusError("Annotation time outside declared recording")
        key = (group_id, source, start, end)
        if key in seen:
            raise CorpusError("Duplicate annotation interval for recording/source")
        seen.add(key)
        seen_sources.add((group_id, source))
        _label(row)
        counts[split] += 1
        for field in FIELDS:
            if field in row:
                coverage[field] += 1
    if any((group_id, source) not in seen_sources
           for group_id, (item, _) in groups.items() for source in item["source_ids"]):
        raise CorpusError("At least one source listed in the manifest has no human annotations")
    return {
        "schema_version": 1, "dataset_id": dataset_id,
        "recording_groups": len(groups), "annotation_segments": len(annotations),
        "segments_by_split": {split: counts[split] for split in SPLITS},
        "annotated_fields": {field: coverage[field] for field in FIELDS},
        "manifest_sha256": manifest_sha, "annotations_sha256": annotations_sha,
        "rights": "declared_only_not_independently_verified",
        "quality": "format_valid_only_not_accuracy_or_inter_annotator_agreement",
        "audio_or_text_exported": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-058: audit a private permitted human-labeled corpus")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional metadata-only JSON report; never overwrite")
    parser.add_argument("--permission-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.permission_confirmed:
            raise CorpusError("Confirm rights and source conditions with --permission-confirmed")
        if args.output and args.output.exists():
            raise CorpusError("Report destination exists; choose a new path")
        manifest, manifest_sha = _read_json(args.manifest)
        annotations, annotations_sha = _read_json(args.annotations)
        result = report(manifest, annotations, manifest_sha=manifest_sha, annotations_sha=annotations_sha)
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
        print(serialized)
    except (CorpusError, OSError) as exc:
        print(f"GN-058: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
