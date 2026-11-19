# CLAUDE.md

## Working rules

- **Do not edit** `submission/FIRST_HOUR.md`.
- **Never touch** `docs/AP_POLICY.md`.
- Every fix needs a test that fails before the fix and passes after it.
- Unit tests must pass offline with `LLM_PROVIDER=fake` (`LLM_PROVIDER=fake make test`).
- Keep changes small and focused. No rewrites.
- Show the diff and wait for approval before any commit.
- No `Co-Authored-By` lines in commit messages.
