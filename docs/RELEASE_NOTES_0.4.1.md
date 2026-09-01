# Whitebox Writing Lab 0.4.1

This patch release keeps the 0.4.0 workflow and authoring features and fixes the Windows release entrypoint so GitHub Actions can build and Sigstore-sign artifacts without depending on a Unicode script path.

Release files are signed through GitHub Actions OIDC, Fulcio, and Rekor. Download the matching `.sigstore.json` file and follow `docs/SIGSTORE.md` to verify provenance and integrity.
