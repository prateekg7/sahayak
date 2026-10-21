# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir "uv==0.11.15"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-install-project
RUN uv sync --frozen --no-dev

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --gid 10001 sahayak \
    && useradd --uid 10001 --gid sahayak --create-home --shell /usr/sbin/nologin sahayak

WORKDIR /app
COPY --from=builder --chown=sahayak:sahayak /app/.venv /app/.venv
COPY --from=builder --chown=sahayak:sahayak /app/src ./src

USER sahayak

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# T2.5 replaces the worker bootstrap with its dedicated runtime.
CMD ["uvicorn", "sahayak.main:app", "--host", "0.0.0.0", "--port", "8000"]
