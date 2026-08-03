import logging
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    retryable: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call fn(), retrying on `retryable` exceptions with exponential backoff + jitter.

    Intended for pre-transaction steps (e.g. verify_connectivity() while Neo4j is
    still booting) — the neo4j driver already retries transient errors inside
    execute_query/execute_write, so this is deliberately not used there.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except retryable as error:
            attempt += 1
            if attempt > retries:
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            delay *= 1 + random.uniform(0, 0.25)
            logger.warning(
                "Attempt %d/%d failed (%s); retrying in %.1fs",
                attempt,
                retries,
                error,
                delay,
            )
            time.sleep(delay)
