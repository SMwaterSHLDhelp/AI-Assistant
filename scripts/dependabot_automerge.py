"""Squash-merge a Dependabot pull request when it is a minor or patch update and checks passed.

This runs from the Dependabot auto-merge workflow, which is triggered by
workflow_run on the default branch. It does not check out the pull request.
Majors are left for a person to merge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

VERSION = r"v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)"
PAIR = re.compile(rf"`?{VERSION}`?\s*(?:->|→|to)\s*`?{VERSION}`?", re.IGNORECASE)
SUCCESS = {"success", "skipped", "neutral"}


def major(version: str) -> str:
    return version.lstrip("v").split("-", 1)[0].split(".", 1)[0]


def version_pairs(text: str) -> list[tuple[str, str]]:
    return [(left, right) for left, right in PAIR.findall(text)]


def eligible(title: str, body: str) -> bool:
    """True for grouped minor/patch updates and for bumps that stay on the same major."""
    if re.search(r"\bmajor\b", title, re.IGNORECASE) and "minor-patch" not in title:
        return False
    pairs = version_pairs(f"{title}\n{body}")
    if pairs and not all(major(left) == major(right) for left, right in pairs):
        return False
    if "minor-patch" in title:
        return True
    return bool(pairs)


def readiness(runs: list[dict[str, str]], status: dict[str, object]) -> str:
    """Return merge, wait, or skip."""
    if int(status.get("total_count") or 0):
        state = str(status.get("state") or "")
        if state == "pending":
            return "wait"
        if state in {"failure", "error"}:
            return "skip"
    relevant = [run for run in runs if "Dependabot auto-merge" not in str(run.get("name") or "")]
    if any(run.get("status") != "completed" for run in relevant):
        return "wait"
    if any(run.get("conclusion") not in SUCCESS for run in relevant):
        return "skip"
    if not any(run.get("conclusion") == "success" for run in relevant):
        return "wait"
    return "merge"


def _gh_json(args: list[str]) -> object:
    raw = subprocess.check_output(["gh", "api", *args], text=True)
    return json.loads(raw) if raw.strip() else None


def pull_requests(repo: str, sha: str) -> list[dict[str, object]]:
    associated = _gh_json(["-H", "Accept: application/vnd.github+json", f"/repos/{repo}/commits/{sha}/pulls"])
    found = [item for item in associated or [] if isinstance(item, dict)]
    if found:
        return found
    listed = subprocess.check_output(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f"sha:{sha}",
            "--json",
            "number,title,body,author,isDraft,headRefOid",
        ],
        text=True,
    )
    data = json.loads(listed) if listed.strip() else []
    return data if isinstance(data, list) else []


def check_runs(repo: str, sha: str) -> list[dict[str, str]]:
    raw = subprocess.check_output(
        [
            "gh",
            "api",
            "--paginate",
            f"/repos/{repo}/commits/{sha}/check-runs",
            "--jq",
            ".check_runs[] | {name,status,conclusion}",
        ],
        text=True,
    )
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def commit_status(repo: str, sha: str) -> dict[str, object]:
    payload = _gh_json([f"/repos/{repo}/commits/{sha}/status"])
    return payload if isinstance(payload, dict) else {}


def author_login(pull: dict[str, object]) -> str:
    user = pull.get("user") or pull.get("author") or {}
    if isinstance(user, dict):
        return str(user.get("login") or "")
    return ""


def head_sha(pull: dict[str, object]) -> str:
    direct = pull.get("headRefOid")
    if isinstance(direct, str) and direct:
        return direct
    head = pull.get("head")
    if isinstance(head, dict) and isinstance(head.get("sha"), str):
        return str(head["sha"])
    return ""


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["HEAD_SHA"]
    pulls = [
        pull
        for pull in pull_requests(repo, sha)
        if author_login(pull) == "dependabot[bot]" and not pull.get("isDraft") and not pull.get("draft")
    ]
    if not pulls:
        print("No open Dependabot pull request for this commit.")
        return 0
    pull = pulls[0]
    number = pull.get("number")
    title = str(pull.get("title") or "")
    body = str(pull.get("body") or "")
    head = head_sha(pull)
    if head and head != sha:
        print(f"Pull request #{number} head does not match {sha}.")
        return 0
    if not eligible(title, body):
        print(f"Leaving #{number} for review: {title}")
        return 0
    decision = readiness(check_runs(repo, sha), commit_status(repo, sha))
    if decision == "wait":
        print(f"Checks for #{number} are still running.")
        return 0
    if decision == "skip":
        print(f"Checks for #{number} did not pass. Not merging.")
        return 0
    print(f"Merging #{number}: {title}")
    subprocess.check_call(["gh", "pr", "merge", str(number), "--repo", repo, "--squash", "--delete-branch"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
