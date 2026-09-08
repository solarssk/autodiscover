#!/usr/bin/env python3
"""Verify a PR's 'Documentation impact' declaration against its actual diff.

Run in CI on pull_request events. Reads the PR body from the GitHub Actions
event payload and compares the declared checkbox against which files the PR
actually changed, so a stale or dishonest declaration fails the check
instead of being trusted on its word.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

DOCS_PATHS = ("docs/", "README.md", "SECURITY.md", "CHANGELOG.md")

DOCS_UPDATED_RE = re.compile(r"^- \[[xX]\] Docs updated\s*$", re.MULTILINE)
NO_DOCS_UPDATE_RE = re.compile(r"^- \[[xX]\] No doc update needed: \S.+$", re.MULTILINE)


def changed_files(base_sha: str, head_sha: str) -> list[str]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...{head_sha}"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [line for line in output.splitlines() if line]


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return 0

    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)

    pull_request = event.get("pull_request")
    if not pull_request:
        return 0

    author_login = (pull_request.get("user") or {}).get("login", "")
    head_ref = (pull_request.get("head") or {}).get("ref", "")
    if author_login == "dependabot[bot]" or head_ref.startswith("dependabot/"):
        return 0

    body = pull_request.get("body") or ""
    docs_updated = bool(DOCS_UPDATED_RE.search(body))
    no_docs_update = bool(NO_DOCS_UPDATE_RE.search(body))

    if docs_updated == no_docs_update:
        print(
            "Select exactly one Documentation impact declaration, "
            "with a real reason if none is needed.",
            file=sys.stderr,
        )
        return 1

    base_sha = pull_request["base"]["sha"]
    head_sha = pull_request["head"]["sha"]
    files = changed_files(base_sha, head_sha)
    docs_changed = any(f.startswith(prefix) for f in files for prefix in DOCS_PATHS)

    if docs_updated and not docs_changed:
        print(
            "'Docs updated' is selected but none of the declared doc paths actually changed.",
            file=sys.stderr,
        )
        return 1
    if no_docs_update and docs_changed:
        print("A declared doc path changed; select 'Docs updated' instead.", file=sys.stderr)
        return 1

    print("Documentation impact declaration is consistent with the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
