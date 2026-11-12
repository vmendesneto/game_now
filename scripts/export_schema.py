"""Export the versioned, standalone JSON Schema used by external clients."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.contracts import ContractBundle  # noqa: E402

if __name__ == "__main__":
    output = ROOT / "schemas" / "v1.schema.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(ContractBundle.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(output)
