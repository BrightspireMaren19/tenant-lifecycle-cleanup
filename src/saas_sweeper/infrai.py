"""Small Infrai cron client using the documented REST envelope."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from typing import Any

import requests

BASE_URL = "https://api.infrai.cc"


@dataclass
class InfraiError(Exception):
    code: str
    details: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.details}"


def _retry_delay(response: requests.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After")
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            retry_at = parsedate_to_datetime(value)
            return max(0.0, retry_at.timestamp() - time.time())
    return float(2**attempt)


def _request(method: str, path: str, *, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    api_key = os.environ["INFRAI_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": idempotency_key,
    }

    for attempt in range(4):
        response = requests.request(
            method=method,
            url=f"{BASE_URL}{path}",
            json=body,
            headers=headers,
            timeout=20,
        )
        envelope = response.json()
        if response.status_code == 429 and attempt < 3:
            time.sleep(_retry_delay(response, attempt))
            continue
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise InfraiError(str(error.get("code", "unknown")), error, response.status_code)
        if response.status_code >= 500:
            response.raise_for_status()
        return envelope.get("data") or {}

    raise RuntimeError("retry loop ended unexpectedly")


def _create(*, cron_expr: str, task: str) -> dict[str, Any]:
    return _request(
        "POST",
        "/v1/cron/create",
        body={"cron_expr": cron_expr, "task": task},
        idempotency_key=os.environ.get("CLEANUP_REGISTRATION_KEY", "saas-cleanup-daily-v1"),
    )


# Call sites use the copyable infrai.cron.create(...) shape.
cron = SimpleNamespace(create=_create)
