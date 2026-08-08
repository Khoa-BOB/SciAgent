FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# sciagent-KG must be present as a sibling directory inside the image --
# kg_service/kg_path.py resolves it at ../sciagent-KG relative to this
# package. See specs/02-kg-service-architecture.md §1.
COPY sciagent-KG /sciagent-KG
COPY sciagent-backend /app

RUN uv sync --frozen --no-dev

EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uv", "run", "uvicorn", "kg_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
