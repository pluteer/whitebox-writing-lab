# Whitebox Writing Lab 0.4.3

This patch isolates the independent Sigstore verifier in a clean Python virtual environment, preventing Ubuntu runner system packages from interfering with Fulcio/Rekor verification.

The GitHub Action's built-in verification and the repository's independent Sigstore CLI verification must both pass before release publication.
