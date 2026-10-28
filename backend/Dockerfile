# Build context: the repository root (the backend depends on packages/savedvariables).
#   docker build -f backend/Dockerfile -t forevertracker-backend .
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /srv

COPY packages/savedvariables /srv/packages/savedvariables
COPY backend/pyproject.toml /srv/backend/pyproject.toml
COPY backend/app /srv/backend/app
RUN pip install /srv/packages/savedvariables /srv/backend

# The simulator is development tooling; production images leave it out.
ARG INSTALL_DEV_TOOLS=false
COPY tools/simulator /tmp/simulator
RUN if [ "$INSTALL_DEV_TOOLS" = "true" ]; then pip install /tmp/simulator; fi && rm -rf /tmp/simulator

COPY backend/alembic.ini /srv/backend/alembic.ini
COPY backend/migrations /srv/backend/migrations

WORKDIR /srv/backend
USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# --proxy-headers: the reverse proxy supplies the client address used for rate limiting
# (hashed in memory, never stored). Restrict FORWARDED_ALLOW_IPS to the proxy in production.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --workers ${WEB_CONCURRENCY:-2}"]
