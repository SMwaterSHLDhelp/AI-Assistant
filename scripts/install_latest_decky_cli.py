"""Download the newest Decky CLI linux binary. Used by the weekly drift workflow."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ASSET_NAME = "decky-linux-x86_64"
RELEASES_URL = "https://api.github.com/repos/SteamDeckHomebrew/cli/releases/latest"


def linux_asset_url(release: dict) -> str:
    matches = [item["browser_download_url"] for item in release.get("assets") or [] if item.get("name") == ASSET_NAME]
    if len(matches) != 1:
        names = sorted(item.get("name", "") for item in release.get("assets") or [])
        raise SystemExit(f"expected one {ASSET_NAME} asset, found {names}")
    return str(matches[0])


def download(dest: Path) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Deckling-drift"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RELEASES_URL, headers=headers)
    with urllib.request.urlopen(request) as response:
        release = json.load(response)
    url = linux_asset_url(release)
    print(f"Decky CLI {release.get('tag_name')} {url}")
    urllib.request.urlretrieve(url, dest)
    dest.chmod(0o755)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: install_latest_decky_cli.py DEST", file=sys.stderr)
        return 2
    download(Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
