"""Open, update, or close the weekly Decky drift issue.

The scheduled workflow calls this after rebuilding against the latest
@decky/ui, @decky/api, and Decky CLI. OUTCOME is success or failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LABEL = "decky-api-drift"
TITLE = "Weekly Decky API drift check failed"


def issue_body(outcome: str, run_url: str, log_text: str) -> str:
    tail = log_text.strip()[-6000:]
    if outcome == "success":
        return f"The weekly Decky drift check passed.\n\n{run_url}\n"
    log_block = f"\n```\n{tail}\n```\n" if tail else "\nNo log was captured.\n"
    return (
        "The weekly rebuild against the latest `@decky/ui`, `@decky/api`, and Decky CLI failed. "
        "This usually means Steam or Decky changed an API this plugin still calls.\n\n"
        f"Run: {run_url}\n"
        f"{log_block}"
    )


def _gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def open_issue_numbers() -> list[str]:
    raw = _gh(
        "issue",
        "list",
        "--label",
        LABEL,
        "--state",
        "open",
        "--json",
        "number",
        "--jq",
        ".[].number",
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def ensure_label() -> None:
    subprocess.run(
        ["gh", "label", "create", LABEL, "--color", "B60205", "--description", "Weekly check against the latest Decky libraries"],
        check=False,
    )


def main() -> int:
    outcome = os.environ.get("OUTCOME", "")
    run_url = os.environ.get("RUN_URL", "")
    log_path = Path(os.environ.get("DRIFT_LOG", ""))
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    body = issue_body(outcome, run_url, log_text)
    if outcome == "success":
        for number in open_issue_numbers():
            subprocess.check_call(["gh", "issue", "comment", number, "--body", body])
            subprocess.check_call(["gh", "issue", "close", number, "--reason", "completed"])
        return 0
    if outcome != "failure":
        print(f"Ignoring outcome {outcome!r}.", file=sys.stderr)
        return 0
    ensure_label()
    numbers = open_issue_numbers()
    if numbers:
        subprocess.check_call(["gh", "issue", "comment", numbers[0], "--body", body])
        return 0
    subprocess.check_call(["gh", "issue", "create", "--title", TITLE, "--label", LABEL, "--body", body])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
