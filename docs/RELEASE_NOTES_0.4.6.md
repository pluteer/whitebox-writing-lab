# Whitebox Writing Lab 0.4.6

## Portable runtime fix

- The launcher now passes the package version explicitly to the frozen API process.
- The API reports the packaged version instead of falling back to an obsolete hard-coded value when the repository root is absent.
- Release version validation now checks the frozen API fallback constant.

This fixes the 0.4.5 portable launcher rejecting a healthy API because the package shell reported 0.4.5 while the frozen API reported 0.4.3.
