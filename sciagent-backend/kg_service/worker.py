"""Ingest worker entrypoint -- run with:

    uv run python -m kg_service.worker

A separate process/container from kg_service.main:app (the read-only API).
Requires KG_WRITE_NEO4J_URI/USERNAME/PASSWORD (read-write Neo4j creds, never
given to the API process) plus REDIS_URL/MINIO_*. See kg_service/jobs.py's
docstring and specs/02-kg-service-architecture.md §8.
"""

import logging

from rq import Worker

from kg_service.deps import get_ingest_queue, get_redis_conn


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    worker = Worker([get_ingest_queue()], connection=get_redis_conn())
    worker.work()


if __name__ == "__main__":
    main()
