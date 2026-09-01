# Whitebox Writing Lab 0.4.4

## Writing review workflow

- Project briefs are injected into chapter workflows and cross-component inputs now preserve the production dependency chain.
- Project-scoped cache keys prevent stale artifacts from being reused across projects, chapters, or canvas revisions.
- Rejected approvals can target the writer, reviewer, or reviser and carry the author's instruction into the rework run.
- Edited author drafts trigger a fresh review, decision, diff, quality gate, and approval before archive.
- Completed runs show actual model calls and token usage; preflight does not estimate usage or cost.

## Web experience

- Added first-run guidance, project deletion, readable run history, and cache/retry status labels.
- Added a full-size manuscript reader for desktop and mobile layouts.
- Improved approval layout, author draft editing, mobile navigation, and stale project selection recovery.

## Reliability

- Fixed SQLite usage aggregation connection scope.
- Increased structured-output budgets for review, arbitration, and revision nodes.
- Added regression coverage for project deletion, author re-review, targeted rework, project isolation, and ten-chapter production.
