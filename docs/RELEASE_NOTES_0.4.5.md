# Whitebox Writing Lab 0.4.5

## Writing workflow

- Project briefs are injected into project-scoped chapter runs.
- Chapter production now exposes a real workflow boundary input, so upstream outline output participates in execution dependencies.
- Cache keys include project, chapter, canvas revision, node configuration, and input artifact hashes.
- Review, arbitration, and revision nodes use larger structured-output budgets.

## Human review

- Rejections can return work to the writer, reviewer, or reviser with durable instructions.
- Author-edited drafts are re-reviewed and receive new decision, diff, quality-gate, and approval evidence before archive.
- Approval notes and rework events remain traceable in the run history.

## Web experience

- Added first-run guidance and complete local project deletion.
- Added desktop and mobile manuscript readers, wider review and history workspaces, clearer cache/retry labels, and project-switch cleanup.
- Preflight shows execution scope and side effects only. Completed runs show actual model calls and token usage.

## Release reliability

- Updated the pinned Sigstore verifier to 4.5.0 for the current production trust root.
- Added regression coverage for project deletion, project isolation, targeted rework, author re-review, and ten-chapter production.
