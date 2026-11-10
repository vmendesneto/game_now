"""Export the versioned, standalone JSON Schema used by external clients."""
import json
from pathlib import Path
from app.contracts import ContractBundle

if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "schemas" / "v1.schema.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(ContractBundle.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
