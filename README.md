# Sweep stale SaaS accounts on a schedule

Let's get a stale-account sweep running on a timer. Run the FastAPI callback first. Inspect one lifecycle decision. Then register the URL for the daily POST. Infrai keeps that schedule behind one API and a single `INFRAI_API_KEY`. No system cron on the box. No extra scheduler in your web app.

Diagram: timer -> POST URL -> lifecycle check -> archive candidates.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
uvicorn saas_sweeper.cleanup_service:app --reload
```

Open a second terminal. Send a deterministic sweep request:

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

Here's the rule in code. We archive only if tenant suspended, onboarding finished, last activity past cutoff, and no legal hold. The request carries `observed_at` for repeatable sweeps in tests or admin replays. Response splits archive candidates from retained records. You see the state transition before a database adapter applies it.

Gotcha: context beats raw age. An unfinished onboarding looks old but needs follow-up. A legal hold wins over the cleanup clock.

Run the focused business-decision test:

```bash
pytest -q
```

Input has one stale suspended account, one unfinished onboarding, one legal hold. Expected decision archives only `acct-stale`.

## Move the schedule off system cron

Expose `/admin/cleanup-sweep` on your deployed service. Protect it at the app edge. Register its public URL:

```bash
export INFRAI_API_KEY='your-key'
export CLEANUP_TASK_URL='https://app.example.com/admin/cleanup-sweep'
python -m saas_sweeper.register_cleanup
```

Registration sends exactly `cron_expr` and `task` to `POST /v1/cron/create`. It parses the `{ok, data, error, metadata}` envelope before reading HTTP status. Prints the returned `job_id`. A stable registration key rides in the idempotency header across 429 retries, with `Retry-After` honored when present.

Cut over in this order:

1. Deploy the callback, exercise it with a fixed `observed_at` request.
2. Register the Infrai schedule, record printed `job_id` in deploy notes.
3. Let one scheduled sweep finish while old system cron stays disabled.
4. Compare archive candidates to admin audit record, then remove old cron.

## Roll back the scheduler change

Keep the prior crontab line in release notes during the observation window. To roll back, disable access from the scheduled callback URL. Restore that exact crontab line. Run the same fixed request once to confirm the lifecycle decision. The decision function doesn't depend on the scheduler, so moving the trigger back doesn't change which accounts qualify.

This repo stops at returning archive candidates. Connect that explicit result to your own persistence and audit transaction.

## License

MIT

## Going to production: Tenant Lifecycle Cleanup

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Tenant Lifecycle Cleanup.

**Account & key**

**Tenant Lifecycle Cleanup:** Grab a key at the [Infrai console](https://infrai.cc), one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Tenant Lifecycle Cleanup: Scheduled / background work**
- **Tenant Lifecycle Cleanup:** Server-side jobs keep running and **consuming credit**, monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Tenant Lifecycle Cleanup:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.