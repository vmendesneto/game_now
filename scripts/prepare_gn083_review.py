"""Prepare a private, prediction-blind human review without accessing media."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.contracts import ContractBundle
from app.storage import DEFAULT_DB
from app.source_validation import validate_source_urls


def prepare(database: Path, match_id: str, source_id: str, destination: Path, *,
            start_seconds: int = 575, duration_seconds: int = 300) -> Path:
    if not 0 <= start_seconds <= 86400 or not 5 <= duration_seconds <= 600:
        raise ValueError('Invalid recording interval')
    if destination.exists():
        raise ValueError('Choose a new destination; review files are never overwritten')
    with closing(sqlite3.connect(f'file:{database.resolve().as_posix()}?mode=ro', uri=True)) as connection:
        row = connection.execute('SELECT payload FROM snapshots WHERE match_id=?', (match_id,)).fetchone()
    if row is None:
        raise ValueError('Match not found')
    bundle = ContractBundle.model_validate_json(row[0])
    source = next((item for item in bundle.sources if item.id == source_id), None)
    if source is None or source.kind != 'youtube' or not source.url:
        raise ValueError('Select the registered permitted YouTube recording')
    validate_source_urls([source])
    data = {'match': bundle.match.model_dump(mode='json'),
            'source_id': source.id, 'source_name': source.name, 'source_url': source.url,
            'requested_media_start_seconds': start_seconds, 'duration_seconds': duration_seconds}
    template = Path(__file__).with_name('templates').joinpath('gn083_review.html').read_text(encoding='utf-8')
    encoded = json.dumps(data, ensure_ascii=False).replace('<', r'\u003c')
    destination.mkdir(parents=True)
    output = destination / 'review.html'
    output.write_text(template.replace('__REVIEW_DATA__', encoded), encoding='utf-8')
    (destination / 'instructions.txt').write_text(
        'GN-083: independent human review. Open review.html locally.\n'
        'Listen to the permitted source independently; no automatic predictions are supplied.\n'
        'Choose only labels supported by the source. Unannotated and absent are different.\n'
        'Several teams, players and regions may be added to each interval; repeated names count once.\n'
        'Export the annotations array and the declaration metadata separately.\n'
        'This is quality validation, not a requirement for operating a match.\n', encoding='utf-8')
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--match-id', required=True)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--start-seconds', type=int, default=575)
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = prepare(args.db, args.match_id, args.source_id, args.output,
                         start_seconds=args.start_seconds, duration_seconds=args.seconds)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, str(exc)+'\n')
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
