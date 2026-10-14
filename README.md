# Minimal deployment scheduler

Only the bounded trigger and its tests live here. No business source, customer
content, database, FTP credentials or personal access token belongs in this repository.

The central service owns job selection, approvals, budgets, leases and verification.
The worker can request only already-authorized work and scheduled maintenance.
It cannot request customer data or create manual backups. Its separate, revocable
key belongs only in the repository secret `CENTRAL_SCHEDULER_KEY`.

Each worker has a finite lifetime. It verifies a fresh nonce-bound authenticated
completion receipt, then hands off using the temporary repository-scoped
`GITHUB_TOKEN`. Scheduled events are only a recovery fallback. There are no
artifacts, caches or private API bodies in public logs.

The workflow is restricted to this public repository and the main branch, on
standard `ubuntu-24.04` runners. If the repository becomes private, it stops.
It runs no pull-request code with credentials. Disable the workflow or set
`SCHEDULER_ENABLED=0` to stop subsequent workers. Revoke the worker key centrally
to invalidate its authority immediately.

Standard public-repository runners are free according to
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
Existing third-party API budgets are unchanged; this does not make external
services or unrelated workflows free.
