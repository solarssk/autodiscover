#!/usr/bin/env bash
# Run the same Python checks as GitHub CI (without Docker/Trivy/gitleaks).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
  RUFF="${ROOT}/.venv/bin/ruff"
  PYTEST="${ROOT}/.venv/bin/pytest"
  MYPY="${ROOT}/.venv/bin/mypy"
  BANDIT="${ROOT}/.venv/bin/bandit"
  PIP_AUDIT="${ROOT}/.venv/bin/pip-audit"
  DEPTRY="${ROOT}/.venv/bin/deptry"
  PIP_COMPILE="${ROOT}/.venv/bin/pip-compile"
else
  PYTHON="python3"
  RUFF="ruff"
  PYTEST="pytest"
  MYPY="mypy"
  BANDIT="bandit"
  PIP_AUDIT="pip-audit"
  DEPTRY="deptry"
  PIP_COMPILE="pip-compile"
fi

echo "==> ruff"
"$RUFF" check .

echo "==> pytest"
"$PYTEST" -q

echo "==> mypy"
"$MYPY" app

echo "==> bandit"
"$BANDIT" -r app -ll -c pyproject.toml

echo "==> requirements.txt (pip-compile drift check)"
# CI regenerates this under Python 3.14 specifically (matching the Dockerfile's
# base image); if your local .venv is a different Python version, pip-compile
# can resolve marker-conditional dependencies differently and report a diff
# here that CI wouldn't actually see, or vice versa.
"$PIP_COMPILE" --generate-hashes --allow-unsafe -o requirements.txt pyproject.toml
git diff --exit-code requirements.txt

if [[ "${SKIP_PIP_AUDIT:-}" != "1" ]]; then
  echo "==> pip-audit"
  # Scoped to requirements.txt (the exact runtime lockfile Dockerfile installs
  # with --require-hashes), matching CI -- not the local .venv's full dev
  # toolchain, which pip-audit would otherwise scan by default.
  "$PIP_AUDIT" -r requirements.txt
fi

if [[ "${SKIP_DEPTRY:-}" != "1" ]]; then
  echo "==> deptry"
  "$DEPTRY" .
fi

echo "All local checks passed."
