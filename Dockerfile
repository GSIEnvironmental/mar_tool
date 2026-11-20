# syntax=docker/dockerfile:1
#
# The build stage installs the app and its locked dependencies with uv. The
# runtime stage copies them into a slim image with Chromium and a non-root user.

# ---------------
# Build
# ---------------
FROM python:3.13-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /src

# Install dependencies before copying the code, so code changes don't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------
# Runtime
# ---------------
FROM python:3.13-slim-bookworm AS runtime

# kaleido needs Chromium to draw the plotly charts in the PDF report.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Run as user 1000
RUN groupadd --gid 1000 mar \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/mar --shell /usr/sbin/nologin mar

COPY --from=build /app/.venv /app/.venv

# osmnx writes its cache to ./cache, so the working directory has to be writable.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    BROWSER_PATH=/usr/bin/chromium \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba

WORKDIR /home/mar
USER 1000:1000
EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/health', timeout=5)"]

STOPSIGNAL SIGTERM
CMD ["mar_dss", "--host", "0.0.0.0", "--port", "8050", "--no-open-browser"]
