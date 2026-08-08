FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Unlike sciagent-backend, this service has no dependency on sciagent-KG --
# it only ever talks to the KG Service over HTTP (specs/00-overview.md).
COPY sciagent-mcp /app

RUN uv sync --frozen --no-dev

# Overridable, but must be 0.0.0.0 (not the config default 127.0.0.1) for the
# container's published port to actually be reachable from outside it.
ENV HOST=0.0.0.0
ENV PORT=8100

EXPOSE 8100
HEALTHCHECK CMD curl -f http://localhost:8100/healthz || exit 1

CMD ["uv", "run", "python", "-m", "mcp_service.server"]
