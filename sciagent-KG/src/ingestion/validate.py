import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver

from src.config import NEO4J_DATABASE, get_driver

logger = logging.getLogger(__name__)

VALIDATION_CYPHER_PATH = Path(__file__).parents[2] / "cypher" / "validation.cypher"


@dataclass
class Check:
    name: str
    description: str
    query: str


@dataclass
class CheckResult:
    check: Check
    violations: int

    @property
    def passed(self) -> bool:
        return self.violations == 0


def parse_checks(cypher_path: Path) -> list[Check]:
    """Parse `-- check: <name>` / `-- description: <text>` blocks separated by
    blank lines into Check objects. Each block's query must return a single
    `violations` column."""
    text = cypher_path.read_text(encoding="utf-8")
    checks = []

    for block in (b.strip() for b in text.split("\n\n")):
        if not block:
            continue

        name = None
        description = ""
        query_lines = []
        for line in block.splitlines():
            if line.startswith("-- check:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("-- description:"):
                description = line.split(":", 1)[1].strip()
            else:
                query_lines.append(line)

        if name is None:
            raise ValueError(f"Validation block missing '-- check:' header: {block!r}")

        checks.append(Check(name=name, description=description, query="\n".join(query_lines).strip()))

    return checks


def run_validation(
    driver: Driver,
    database: str | None = NEO4J_DATABASE,
    checks: list[Check] | None = None,
) -> list[CheckResult]:
    checks = checks if checks is not None else parse_checks(VALIDATION_CYPHER_PATH)
    results = []
    for check in checks:
        records, _, _ = driver.execute_query(
            check.query, database_=database, routing_="r"
        )
        violations = records[0]["violations"] if records else 0
        results.append(CheckResult(check=check, violations=violations))
    return results


def print_report(results: list[CheckResult]) -> bool:
    all_passed = True
    width = max((len(r.check.name) for r in results), default=0)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            all_passed = False
        print(f"{result.check.name.ljust(width)}  {status}  violations={result.violations}")
        if not result.passed:
            print(f"  {result.check.description}")
    return all_passed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run post-load sanity checks against the graph."
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: %(default)s)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )

    driver = get_driver()
    try:
        results = run_validation(driver)
        all_passed = print_report(results)
    finally:
        driver.close()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
