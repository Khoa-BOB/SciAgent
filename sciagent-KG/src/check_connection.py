import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


uri = os.getenv("NEO4J_URI")
username = os.getenv("NEO4J_USERNAME")
password = os.getenv("NEO4J_PASSWORD")
database = os.getenv("NEO4J_DATABASE")

driver = GraphDatabase.driver(uri, auth=(username, password))

def check_connection():
    with driver.session(database=database) as session:
        result = session.run("RETURN 1")
        return result.single()[0] == 1

if __name__ == "__main__":
    if check_connection():
        print("Connection successful")
    else:
        print("Connection failed")
