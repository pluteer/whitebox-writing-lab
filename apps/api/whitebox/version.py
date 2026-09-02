from pathlib import Path
import json
import os


PACKAGE_VERSION = "0.4.6"


def get_version() -> str:
    runtime_version = os.getenv("WHITEBOX_VERSION")
    if runtime_version:
        return runtime_version
    version_file = Path(__file__).resolve().parents[3] / "version.json"
    try:
        return str(json.loads(version_file.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return PACKAGE_VERSION
