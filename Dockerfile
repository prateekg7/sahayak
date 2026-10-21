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

# T0.5 replaces this import-level health check with the /healthz endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sahayak" || exit 1

# T0.5 and T2.5 replace the bootstrap commands with the web application and worker.
CMD ["python", "-m", "sahayak.container", "app"]
