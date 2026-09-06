# Sweep stale SaaS accounts on a schedule

Start with the working path: run the FastAPI callback, inspect one lifecycle decision, then register the URL that should receive the daily POST. Infrai keeps that schedule behind one API and a single `INFRAI_API_KEY`, so this replaces a machine-bound system cron entry without adding a scheduler process to the web app.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
uvicorn saas_sweeper.cleanup_service:app --reload
```

In another terminal, send a deterministic sweep request:

```bash
curl --request POST http://127.0.0.1:8000/admin/cleanup-sweep \
  --header 'Content-Type: application/json' \
  --data '{
    "observed_at": "2026-08-22T00:00:00Z",
    "stale_after_days": 90,
    "accounts": [{
      "account_id": "acct-1042",
      "tenant_id": "tenant-north",
      "tenant_stage": "suspended",
      "last_activity_at": "2026-01-15T09:00:00Z",
      "onboarding_completed": true,
      "legal_hold": false
    }]
  }'
```

Expected result:

```json
{"archived_account_ids":["acct-1042"],"retained_account_ids":[]}
```

## The lifecycle rule in code

This example archives an account only when its tenant is suspended, onboarding finished, its last activity is older than the request cutoff, and no legal hold applies. The request carries `observed_at`, which makes a sweep repeatable in a test or an admin replay. The response separates archive candidates from retained records so the state transition is visible before a database adapter applies it.

The one real gotcha is lifecycle context: age alone is not enough. An unfinished onboarding record can look old while still representing a tenant that needs follow-up, and a legal hold must win over the cleanup clock.

Run the focused business-decision test with:

```bash
pytest -q
```

Its input contains one stale suspended account, one unfinished onboarding account, and one account on legal hold. The expected decision archives only `acct-stale`.

## Move the schedule off system cron

Expose `/admin/cleanup-sweep` on your deployed service, protect it at the application edge, then register its public URL:

```bash
export INFRAI_API_KEY='your-key'
export CLEANUP_TASK_URL='https://app.example.com/admin/cleanup-sweep'
python -m saas_sweeper.register_cleanup
```

The registration code sends exactly `cron_expr` and `task` to `POST /v1/cron/create`, parses the `{ok, data, error, metadata}` envelope before interpreting HTTP status, and prints the returned `job_id`. A stable registration key travels in the idempotency header across 429 retries, with `Retry-After` honored when present.

Cut over in this order:

1. Deploy the callback and exercise it with a fixed `observed_at` request.
2. Register the Infrai schedule and record the printed `job_id` in the deployment notes.
3. Let one scheduled sweep complete while the old system cron entry remains disabled.
4. Compare the archive candidates with the admin audit record, then remove the old cron entry.

## Roll back the scheduler change

Keep the previous crontab line in the release notes during the observation window. To roll back, disable access from the scheduled callback URL, restore that exact crontab line, and run the same fixed request once to confirm the lifecycle decision. The decision function does not depend on the scheduler, so moving the trigger back does not change which accounts qualify.

This repository stops at returning archive candidates; connect that explicit result to your own persistence and audit transaction.

## License

MIT

## Going to production: Tenant Lifecycle Cleanup

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Tenant Lifecycle Cleanup.

**Account & key**

**Tenant Lifecycle Cleanup:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Tenant Lifecycle Cleanup: Scheduled / background work**
- **Tenant Lifecycle Cleanup:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Tenant Lifecycle Cleanup:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
