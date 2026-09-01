from pathlib import Path
import json


def get_version() -> str:
    version_file = Path(__file__).resolve().parents[3] / "version.json"
    try:
        return str(json.loads(version_file.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return "0.4.1"
