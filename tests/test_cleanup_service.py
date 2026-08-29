from datetime import datetime, timezone

from saas_sweeper.cleanup_service import SweepRequest, decide_cleanup


def test_only_stale_completed_suspended_accounts_are_archived() -> None:
    request = SweepRequest.model_validate(
        {
            "observed_at": datetime(2026, 8, 22, tzinfo=timezone.utc),
            "stale_after_days": 90,
            "accounts": [
                {
                    "account_id": "acct-stale",
                    "tenant_id": "tenant-a",
                    "tenant_stage": "suspended",
                    "last_activity_at": "2026-01-01T00:00:00Z",
                    "onboarding_completed": True,
                },
                {
                    "account_id": "acct-onboarding",
                    "tenant_id": "tenant-b",
                    "tenant_stage": "onboarding",
                    "last_activity_at": "2026-01-01T00:00:00Z",
                    "onboarding_completed": False,
                },
                {
                    "account_id": "acct-held",
                    "tenant_id": "tenant-c",
                    "tenant_stage": "suspended",
                    "last_activity_at": "2026-01-01T00:00:00Z",
                    "onboarding_completed": True,
                    "legal_hold": True,
                },
            ],
        }
    )

    result = decide_cleanup(request)

    assert result.archived_account_ids == ["acct-stale"]
    assert result.retained_account_ids == ["acct-onboarding", "acct-held"]
