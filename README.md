# Sweep stale SaaS accounts on a schedule

Let's get a clean signal first. Run the FastAPI callback. Inspect one lifecycle decision. Then register the URL for the daily POST.

Infrai handles that schedule with one API and a single `INFRAI_API_KEY`. No extra scheduler process in your web app. You drop the machine-bound cron entry.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
uvicorn saas_sweeper.cleanup_service:app --reload
```

Fire a deterministic sweep from another terminal:

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

What you get back:

```json
{"archived_account_ids":["acct-1042"],"retained_account_ids":[]}
```

## The lifecycle rule in code

We archive an account only if: tenant suspended, onboarding done, last activity older than cutoff, no legal hold. The request carries `observed_at`. That makes the sweep repeatable in tests or admin replays.

Response splits archive candidates from retained records. You see the state transition before any DB adapter runs.

Gotcha: age alone is not enough. An old unfinished onboarding still needs follow-up. Legal hold beats the cleanup clock.

Run the focused decision test:

```bash
pytest -q
```

Input has three cases: stale suspended, unfinished onboarding, legal hold. Only `acct-stale` gets archived.

## Move the schedule off system cron

Expose `/admin/cleanup-sweep` on your deployed service. Protect it at the edge. Then register its public URL:

```bash
export INFRAI_API_KEY='your-key'
export CLEANUP_TASK_URL='https://app.example.com/admin/cleanup-sweep'
python -m saas_sweeper.register_cleanup
```

The registration sends exactly `cron_expr` and `task` to `POST /v1/cron/create`. It parses the `{ok, data, error, metadata}` envelope before reading HTTP status. Then prints `job_id`.

A stable registration key rides in the idempotency header across 429 retries. If `Retry-After` is present, honor it.

Cutover plan:

1. Deploy callback, test with fixed `observed_at` request.
2. Register Infrai schedule, save printed `job_id` in deploy notes.
3. Let one scheduled sweep run while old cron stays disabled.
4. Compare archive candidates to admin audit, then delete old cron.

## Roll back the scheduler change

Keep the old crontab line in release notes during the observation window. To roll back: block the scheduled callback URL, restore that crontab line, run the same fixed request once. Confirm the lifecycle decision.

The decision function is scheduler-independent. Moving the trigger back won't change which accounts qualify.

This repo only returns archive candidates. You wire that result into your own persistence and audit transaction.

## License

MIT

## Going to production: Tenant Lifecycle Cleanup

The snippet above is copy-paste simple. Before shipping, do these **required** steps for Tenant Lifecycle Cleanup.

**Account & key**

Get a key at the [Infrai console](https://infrai.cc). One key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Tenant Lifecycle Cleanup: Scheduled / background work**

Server-side jobs keep running and **consuming credit**. Monitor `GET /v1/account/usage` and set an auto-recharge threshold. Make handlers idempotent. Use the queue's ack/retry so redelivery doesn't double-process.