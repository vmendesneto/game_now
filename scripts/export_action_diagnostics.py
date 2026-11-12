"""Explicitly save a text-only reanalysis for later inspection; never auto-run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from app.action_diagnostics import MAX_ARCHIVE_BYTES, archive_path
from app.contracts import Match


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id",required=True)
    parser.add_argument("--port",type=int,default=8000,choices=range(1,65536))
    parser.add_argument("--input",type=Path,help="Previously exported diagnostic JSON, not audio")
    parser.add_argument("--output-dir",type=Path,default=Path(__file__).resolve().parents[1]/"data"/"action-audits")
    args=parser.parse_args()
    if args.input:
        if args.input.stat().st_size>MAX_ARCHIVE_BYTES:parser.error("Input too large")
        report=json.loads(args.input.read_text(encoding="utf-8"))
    else:
        with urlopen(f"http://127.0.0.1:{args.port}/api/matches/{quote(args.match_id,safe='')}/actions/diagnostics",timeout=30) as response:
            raw=response.read(MAX_ARCHIVE_BYTES+1)
        if len(raw)>MAX_ARCHIVE_BYTES:parser.error("Response too large")
        report=json.loads(raw)
    if report.get("match_id")!=args.match_id or report.get("basis")!="reanalysis_of_retained_text_with_current_roster":
        parser.error("Unexpected diagnostic report")
    Match.model_validate(report["match"])
    report["saved_at"]=datetime.now(timezone.utc).isoformat()
    encoded=json.dumps(report,ensure_ascii=False,indent=2).encode("utf-8")
    if len(encoded)>MAX_ARCHIVE_BYTES:parser.error("Report too large")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    path=archive_path(args.output_dir,args.match_id)
    path.write_bytes(encoded)
    print(json.dumps({"saved":str(path),"windows":len(report["windows"]),"text_only":True,"match_state_changed":False}))


if __name__=="__main__":main()
