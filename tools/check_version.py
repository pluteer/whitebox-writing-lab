from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    version = str(read_json(ROOT / "version.json")["version"])
    if not VERSION_PATTERN.fullmatch(version):
        raise SystemExit(f"Invalid version: {version}")
    checks = {
        "apps/api/pyproject.toml": f'version = "{version}"',
        "apps/web/package.json": f'"version": "{version}"',
        "launcher/WhiteboxLauncher.ps1": f'$LauncherVersion = "{version}"',
        "launcher/README.md": f"whitebox-writing-portable-{version}.zip",
        "installer/Whitebox.iss": f'#define AppVersion "{version}"',
        "apps/api/whitebox/version.py": f'PACKAGE_VERSION = "{version}"',
    }
    errors = [path for path, marker in checks.items() if marker not in (ROOT / path).read_text(encoding="utf-8")]
    if errors:
        raise SystemExit("Version mismatch: " + ", ".join(errors))
    if len(sys.argv) > 1:
        if sys.argv[1] != "--tag" or len(sys.argv) != 3:
            raise SystemExit("Usage: check_version.py [--tag vMAJOR.MINOR.PATCH]")
        expected_tag = f"v{version}"
        if sys.argv[2] != expected_tag:
            raise SystemExit(f"Release tag {sys.argv[2]!r} does not match {expected_tag!r}")
    print(f"version {version} is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
