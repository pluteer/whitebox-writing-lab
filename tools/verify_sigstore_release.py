from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Sigstore release materials before publication.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--verify-signatures", action="store_true", help="Cryptographically verify every artifact with sigstore-python")
    parser.add_argument("--certificate-identity", help="Expected Fulcio certificate identity")
    parser.add_argument("--oidc-issuer", default="https://token.actions.githubusercontent.com")
    args = parser.parse_args()
    directory = args.directory.resolve()
    artifacts = sorted(path for path in directory.iterdir() if path.is_file() and path.suffix in {".zip", ".exe", ""} and path.name != "SHA256SUMS")
    if not artifacts:
        raise SystemExit("No release artifacts found")
    expected = [*artifacts, directory / "SHA256SUMS"]
    errors: list[str] = []
    for artifact in expected:
        bundle = artifact.with_name(artifact.name + ".sigstore.json")
        if not bundle.is_file():
            errors.append(f"missing bundle for {artifact.name}")
            continue
        try:
            payload = json.loads(bundle.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"invalid bundle for {artifact.name}")
            continue
        if not payload.get("verificationMaterial") or not payload.get("messageSignature"):
            errors.append(f"incomplete bundle for {artifact.name}")
        if args.verify_signatures:
            if not args.certificate_identity:
                errors.append("--certificate-identity is required with --verify-signatures")
                continue
            result = subprocess.run(
                [
                    sys.executable, "-m", "sigstore", "verify", "identity",
                    "--bundle", str(bundle),
                    "--cert-identity", args.certificate_identity,
                    "--cert-oidc-issuer", args.oidc_issuer,
                    str(artifact),
                ],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                errors.append(f"signature verification failed for {artifact.name}: {result.stderr.strip()}")
    if errors:
        raise SystemExit("Sigstore verification material check failed: " + "; ".join(errors))
    print(f"Sigstore bundles present for {len(expected)} signed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
