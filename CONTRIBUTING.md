# Contributing

Keep infrastructure changes reviewable and tied to their versioned owner. Read
`AGENTS.md` and the relevant change-control document before editing host,
network, storage, or guest state. Preserve existing work in a dirty checkout.

## Branches and commits

- Work on a named feature branch; do not push directly to `main`.
- Stage exact paths and review `git diff --cached` before each commit. Never
  stage `secrets/`, credentials, private keys, state, decrypted files, saved
  plans, local caches, or runtime backups. Keep `.planning/` session handoffs
  and scratch notes local unless a specific artifact is intentionally selected
  for the review.
- Use Conventional Commit subjects (`type(scope): imperative summary`) and keep
  commits focused on one independently reviewable concern.
- Push the feature branch to `upstream` and open a pull request against `main`.
  Include the change's purpose, affected resource owners, verification, and any
  live-state or recovery limitations. Do not merge or apply infrastructure as
  part of preparing a pull request.

## Verification

Run checks for the changed layer and report unavailable checks honestly. For
OpenTofu changes, run formatting, validation, plan-safety tests, and inspect the
plan; never apply during pull-request validation. For Ansible changes, run a
syntax check and check mode where meaningful. For host shell scripts, run
`bash -n` and their non-mutating check/test paths. For OpenSpec changes, run
strict validation. For Python changes, run relevant tests, formatting, lint,
and strict type checks when available. Always run `git diff --check` and a
secret scan over the candidate changes before committing. Confirm the pushed
branch and commit SHA, then inspect the pull request's current checks before
describing it as ready.
