import os

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def validate_config() -> None:
    """Raise a clear error naming any missing required Neo4j env vars."""
    missing = [
        name
        for name, value in (
            ("NEO4J_URI", NEO4J_URI),
            ("NEO4J_USERNAME", NEO4J_USERNAME),
            ("NEO4J_PASSWORD", NEO4J_PASSWORD),
        )
        if not value
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in sciagent-KG/.env."
        )


def get_driver() -> Driver:
    """Build a Neo4j driver from validated config. Caller owns closing it."""
    validate_config()
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
