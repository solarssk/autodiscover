#!/usr/bin/env python3
"""Format CHANGELOG sections into GitHub Release notes."""

from __future__ import annotations

import re
import sys
from collections import OrderedDict
from pathlib import Path

SECTION_EMOJI = {
    "added": "✨ Added",
    "changed": "🔄 Changed",
    "deprecated": "⚠️ Deprecated",
    "removed": "🗑️ Removed",
    "fixed": "🐛 Fixed",
    "security": "🔒 Security",
    "note": "📝 Note",
}

SUMMARY_SECTIONS = ("What's new", "What this means", "Action required")

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
GHCR_IMAGE = "ghcr.io/solarssk/mail-autodiscover"
DOCKERHUB_IMAGE = "docker.io/solarssk/mail-autodiscover"


def parse_version(tag: str) -> str:
    return tag.removeprefix("v")


def extract_section(changelog: str, version: str) -> str:
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, changelog, flags=re.MULTILINE | re.DOTALL)
    if not match:
        msg = f"No CHANGELOG section found for version {version}"
        raise SystemExit(msg)
    section = match.group(1).strip()
    section = re.sub(r"\n\[[^\n]+\]:\s+https?://[^\n]+", "", section, flags=re.MULTILINE)
    return section.strip()


def parse_subsections(body: str) -> OrderedDict[str, list[str]]:
    sections: OrderedDict[str, list[str]] = OrderedDict()
    current_heading: str | None = None

    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            current_heading = line.removeprefix("### ").strip()
            sections[current_heading] = []
            continue
        if current_heading is None:
            continue
        sections[current_heading].append(line)

    return sections


def normalize_lines(lines: list[str]) -> list[str]:
    trimmed = [line.rstrip() for line in lines]

    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    while trimmed and not trimmed[-1]:
        trimmed.pop()

    return trimmed


def format_summary_block(sections: OrderedDict[str, list[str]]) -> str:
    labels = {
        "What's new": "✨ What's new",
        "What this means": "🎯 What this means",
        "Action required": "🛠️ Action required",
    }
    lines = ["## At a glance", ""]

    for heading in SUMMARY_SECTIONS:
        content = normalize_lines(sections.get(heading, []))
        if not content and heading == "Action required":
            content = ["- No action required."]
        if not content:
            continue
        lines.append(f"### {labels[heading]}")
        lines.append("")
        lines.extend(content)
        lines.append("")

    return "\n".join(lines).strip()


def format_technical_sections(sections: OrderedDict[str, list[str]]) -> str:
    lines: list[str] = []

    for heading, content in sections.items():
        if heading in SUMMARY_SECTIONS:
            continue
        normalized = normalize_lines(content)
        if not normalized:
            continue
        emoji_heading = SECTION_EMOJI.get(heading.lower(), f"📌 {heading}")
        lines.append(f"### {emoji_heading}")
        lines.append("")
        lines.extend(normalized)
        lines.append("")

    return "\n".join(lines).strip()


def docker_block(version: str, prerelease: bool) -> str:
    tag = version
    lines = [
        "---",
        "",
        "## 🐳 Docker tags",
        "",
        "```text",
        f"{GHCR_IMAGE}:{tag}",
        f"{DOCKERHUB_IMAGE}:{tag}",
    ]
    if not prerelease and "-" not in tag:
        lines.append(f"{GHCR_IMAGE}:latest")
        lines.append(f"{DOCKERHUB_IMAGE}:latest")
    lines.extend(
        [
            "```",
            "",
            "**Portainer / production:** pin the semver tag, not `latest`.",
            "",
            "## 📚 Useful links",
            "",
            "- [Full CHANGELOG](https://github.com/solarssk/mail-autodiscover/blob/main/CHANGELOG.md)",
            "- [README](https://github.com/solarssk/mail-autodiscover)",
            "- [Wiki](https://github.com/solarssk/mail-autodiscover/wiki)",
            "- [.env.example](https://github.com/solarssk/mail-autodiscover/blob/main/.env.example)",
        ]
    )
    return "\n".join(lines)


def build_release_notes(version: str, prerelease: bool = False) -> str:
    changelog = CHANGELOG.read_text(encoding="utf-8")
    body = extract_section(changelog, version)
    sections = parse_subsections(body)
    summary = format_summary_block(sections)
    technical = format_technical_sections(sections)

    header = f"## 🚀 mail-autodiscover v{version}"
    if prerelease:
        header += " (pre-release)"

    parts = [header, "", summary]
    if technical:
        parts.extend(["", "## 🔧 Technical details", "", technical])
    parts.extend(["", docker_block(version, prerelease)])
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: format_release_notes.py <tag>   e.g. v0.1.1")

    tag = sys.argv[1]
    version = parse_version(tag)
    prerelease = "-" in version
    sys.stdout.write(build_release_notes(version, prerelease=prerelease))


if __name__ == "__main__":
    main()
