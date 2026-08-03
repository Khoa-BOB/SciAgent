from neo4j import Driver

from src.config import NEO4J_DATABASE, get_driver


def check_connection(driver: Driver, database: str | None = NEO4J_DATABASE) -> bool:
    with driver.session(database=database) as session:
        result = session.run("RETURN 1")
        return result.single()[0] == 1


if __name__ == "__main__":
    driver = get_driver()
    try:
        if check_connection(driver):
            print("Connection successful")
        else:
            print("Connection failed")
    finally:
        driver.close()
