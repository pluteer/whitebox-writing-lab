# Whitebox Writing Lab 0.4.0

## Highlights

- Official book-production workflow enabled for every new project.
- ComfyUI-style standalone workflows start with zero nodes and zero edges.
- Auto Director creates multiple book directions and persists the confirmed checkpoint.
- Chapter production includes drafting, independent review, arbitration, targeted revision, Diff, quality gate, approval, archive, and StatePatch proposal.
- Author draft workspace saves edits as versioned project assets without mutating immutable Artifacts.
- Prompt packs support project overrides, history, Diff, restore, deletion, and runtime snapshots.
- Run history supports filtering, recovery, and cross-run node comparison.
- Project bundles support safe round-trip import/export with path and hash validation.
- API default port moved to `8001`; `8000` remains free for other local services.

## Verification

- Backend test baseline: 103+ tests.
- Frontend tests: 15 tests.
- TypeScript and production Vite build pass.
- Project export excludes provider secrets and API keys.
