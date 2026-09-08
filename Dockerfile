# Pin to bookworm for predictable Debian security updates.
# Dependabot proposes digest bumps via .github/dependabot.yml (docker ecosystem).
FROM python:3.14-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY app ./app
# app/static includes favicon.ico and apple-touch-icon.png
# pip is removed after install: the app runs via uvicorn and never invokes pip
# at runtime, and pip vendors its own copies of packages like msgpack and
# pkg_resources/setuptools that periodically pick up CVEs of their own
# (unrelated to anything this app actually uses) if left in the shipped image.
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && pip install --no-cache-dir . \
    && pip uninstall -y pip

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"CONTAINER_PORT\", \"8000\")}/health')"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${CONTAINER_PORT:-8000} --no-access-log"]
