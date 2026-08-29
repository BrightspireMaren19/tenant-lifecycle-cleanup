"""HTTP entry point for a periodic B2B SaaS account cleanup sweep."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    BaseModel = None  # type: ignore[assignment,misc]


class TenantStage(str, Enum):
    onboarding = "onboarding"
    active = "active"
    suspended = "suspended"


if BaseModel is not None:
    class AccountRecord(BaseModel):
        account_id: str
        tenant_id: str
        tenant_stage: TenantStage
        last_activity_at: datetime
        onboarding_completed: bool
        legal_hold: bool = False


    class SweepRequest(BaseModel):
        observed_at: datetime
        stale_after_days: int = Field(default=90, ge=1, le=3650)
        accounts: list[AccountRecord]


    class SweepResult(BaseModel):
        archived_account_ids: list[str]
        retained_account_ids: list[str]
else:
    from dataclasses import dataclass

    def _datetime(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


    @dataclass
    class AccountRecord:
        account_id: str
        tenant_id: str
        tenant_stage: TenantStage
        last_activity_at: datetime
        onboarding_completed: bool
        legal_hold: bool = False


    @dataclass
    class SweepRequest:
        observed_at: datetime
        accounts: list[AccountRecord]
        stale_after_days: int = 90

        @classmethod
        def model_validate(cls, value: dict[str, object]) -> "SweepRequest":
            accounts = [
                AccountRecord(
                    account_id=str(account["account_id"]),
                    tenant_id=str(account["tenant_id"]),
                    tenant_stage=TenantStage(account["tenant_stage"]),
                    last_activity_at=_datetime(account["last_activity_at"]),
                    onboarding_completed=bool(account["onboarding_completed"]),
                    legal_hold=bool(account.get("legal_hold", False)),
                )
                for account in value["accounts"]  # type: ignore[union-attr]
            ]
            stale_after_days = int(value.get("stale_after_days", 90))
            if not 1 <= stale_after_days <= 3650:
                raise ValueError("stale_after_days must be between 1 and 3650")
            return cls(
                observed_at=_datetime(value["observed_at"]),  # type: ignore[arg-type]
                stale_after_days=stale_after_days,
                accounts=accounts,
            )


    @dataclass
    class SweepResult:
        archived_account_ids: list[str]
        retained_account_ids: list[str]


def decide_cleanup(request: SweepRequest) -> SweepResult:
    cutoff = request.observed_at.astimezone(timezone.utc) - timedelta(days=request.stale_after_days)
    archived: list[str] = []
    retained: list[str] = []
    for account in request.accounts:
        eligible = (
            account.tenant_stage == TenantStage.suspended
            and account.onboarding_completed
            and not account.legal_hold
            and account.last_activity_at.astimezone(timezone.utc) < cutoff
        )
        (archived if eligible else retained).append(account.account_id)
    return SweepResult(archived_account_ids=archived, retained_account_ids=retained)


try:
    from fastapi import FastAPI
except ModuleNotFoundError:
    app = None
else:
    app = FastAPI(title="SaaS stale-account sweeper")

    @app.post("/admin/cleanup-sweep", response_model=SweepResult)
    def cleanup_sweep(request: SweepRequest) -> SweepResult:
        """Return the lifecycle decision that a persistence adapter can apply."""
        return decide_cleanup(request)
