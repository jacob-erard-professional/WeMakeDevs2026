FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /srv
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml
COPY app/ app/

ARG APP_VERSION=dev
ENV PORT=8080 APP_VERSION=$APP_VERSION PYTHONUNBUFFERED=1
# Numeric user so the pod's runAsNonRoot check can verify it.
USER 1000
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
