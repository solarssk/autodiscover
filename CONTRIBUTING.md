# Contributing

Thank you for contributing to **mail-autodiscover**.

## Workflow

All changes to `main` must go through a **pull request**. Direct pushes to `main` are blocked by branch protection.

1. Create a branch from `main`:
   ```bash
   git checkout main
   git pull
   git checkout -b feat/your-change
   ```
2. Make your changes and add tests where relevant.
3. Install dev tools once:
   ```bash
   pip install ".[dev]"
   pre-commit install
   ```
   After that, `ruff`, `mypy`, and `pytest` run automatically before each `git commit`.
4. Before pushing, run the full local CI mirror (optional but recommended):
   ```bash
   ./scripts/check.sh
   ```
   Skip slower dependency scans when needed:
   ```bash
   SKIP_PIP_AUDIT=1 SKIP_DEPTRY=1 ./scripts/check.sh
   ```
5. Open a pull request against `main`.
6. Wait for all CI checks to pass.
7. Merge when ready (squash merge is fine).

## Dependencies

Runtime dependencies (`[project.dependencies]` in `pyproject.toml`) are locked in
`requirements.txt`, a hash-pinned file generated with `pip-compile`. This is what the
Docker image actually installs from, so the exact same versions and artifacts get
installed on every build instead of whatever happens to satisfy the `>=` bounds in
`pyproject.toml` on a given day.

Whenever you add, remove, or change a runtime dependency, regenerate the lockfile in the
same PR:

```bash
pip-compile --generate-hashes --allow-unsafe -o requirements.txt pyproject.toml
```

CI fails the PR if `requirements.txt` doesn't match what regenerating it produces, so
this can't be forgotten silently. Dev-only tools
(`[project.optional-dependencies].dev`) are deliberately not locked: they never ship in
the container, and locking them too would double the maintenance surface for little
practical benefit.

## CI checks

| Check | What it does |
|-------|----------------|
| Secret scan (gitleaks) | Scans this run's own commit range for leaked secrets |
| Documentation impact declaration | Verifies the PR's "Documentation impact" checkbox against the actual diff (skipped for Dependabot PRs) |
| Lint (ruff) | Python style and lint |
| Tests and coverage | `pytest` with ≥90% coverage on `app/`; also uploads to Codecov and runs a SonarCloud scan (both report-only, not merge gates yet) |
| Type check (mypy) | Static typing on `app/` |
| Security (bandit + pip-audit) | Code and dependency security |
| Docker build and scan | Image build + Trivy scan (blocks HIGH/CRITICAL on PR; advisory SARIF upload on `main`) |

`docker-publish.yml` additionally builds each published platform (`linux/amd64`,
`linux/arm64`) once, pushes it by digest, and scans and gates that exact digest on
fixable CRITICAL before the real `latest`/version tags are ever created from it. A
CycloneDX SBOM per platform is attached to the GitHub Release on version tags. See
[SECURITY.md](SECURITY.md#security-controls--ci) for the full control-to-workflow mapping.

## Labels

Use labels to classify issues and PRs:

| Label | When to use |
|-------|-------------|
| `bug` | Something is broken |
| `enhancement` | New feature or improvement |
| `documentation` | Docs only |
| `security` | Security hardening or vulnerability |
| `testing` | Tests and coverage |
| `ci/cd` | CI, releases, GHCR |
| `dependencies` | Dependency updates (often Dependabot) |
| `outlook` | Outlook Autodiscover |
| `thunderbird` | Thunderbird Autoconfig |
| `mail-server` | Synology / IMAP / SMTP integration topics |

## Releases

- Merge **all** open PRs (including Dependabot) before cutting a release.
- Update `CHANGELOG.md` and `pyproject.toml` version on `main` via PR.
- Images are published to **GHCR** on every push to `main` and on version tags `v*`.

Keep the audience in mind:

- `README.md` is the user/admin landing page.
- the `docs/` directory contains the user and admin documentation.
- `CONTRIBUTING.md` stays maintainer-focused.

### CHANGELOG format

Each release entry should begin with the plain-language sections below:

- `### What's new`
- `### What this means`
- `### Action required`

After that, use [Keep a Changelog](https://keepachangelog.com/) sections for the technical breakdown. They map to emoji in release notes:

| CHANGELOG | Release section |
|-----------|-----------------|
| `### Added` | ✨ Added |
| `### Changed` | 🔄 Changed |
| `### Fixed` | 🐛 Fixed |
| `### Security` | 🔒 Security |
| `### Note` | 📝 Note |

If no upgrade step is needed, write `- No action required.`

### Cut a release

After `main` is clean:

```bash
git checkout main && git pull
git tag v0.1.2
git push origin v0.1.2
```

The **Release** workflow reads `CHANGELOG.md` and publishes formatted notes with:

- a short human summary,
- a clear `Action required` or `No action required` section,
- the technical emoji sections,
- Docker tags and documentation links.

Preview locally:

```bash
python scripts/format_release_notes.py v0.1.2
```

Manual release (same formatting):

```bash
python scripts/format_release_notes.py v0.1.2 > /tmp/notes.md
gh release create v0.1.2 --target main --title "v0.1.2" --notes-file /tmp/notes.md
```

## Security

See [SECURITY.md](SECURITY.md). Do not open public issues for vulnerabilities — use GitHub private security advisories.
