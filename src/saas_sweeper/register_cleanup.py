"""Register the daily cleanup callback with Infrai."""

from __future__ import annotations

import argparse
import os

from saas_sweeper import infrai


def register(task_url: str) -> str:
    result = infrai.cron.create(
        cron_expr="15 2 * * *",
        task=task_url,
    )
    return str(result["job_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the stale-account cleanup sweep")
    parser.add_argument("--task-url", default=os.environ.get("CLEANUP_TASK_URL"), required=False)
    args = parser.parse_args()
    if not args.task_url:
        parser.error("set CLEANUP_TASK_URL or pass --task-url")
    job_id = register(args.task_url)
    print(f"Cleanup sweep scheduled with job_id={job_id}")


if __name__ == "__main__":
    main()
