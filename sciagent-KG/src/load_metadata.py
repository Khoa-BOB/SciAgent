import json

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

sample_path = Path("../data/example/example.jsonl")
uri = os.getenv("NEO4J_URI")
username = os.getenv("NEO4J_USERNAME")
password = os.getenv("NEO4J_PASSWORD")
database = os.getenv("NEO4J_DATABASE")

QUERY = """
    MERGE (p:Paper {arxiv_id: $arxiv_id})
    SET
        p.title = $title,
        p.abstract = $abstract,
        p.update_date = $update_date

    WITH p
    UNWIND $authors AS author
    MERGE (a:Author {author_id: author.author_id})
    SET
        a.name = author.name,
        a.family_name = author.family_name,
        a.given_names = author.given_names
    MERGE (a)-[r:AUTHORED]->(p)
    SET r.position = author.position

    WITH p
    UNWIND $categories AS category
    MERGE (c:Category {code: category.code})
    MERGE (p)-[r:IN_CATEGORY]->(c)
    SET
        r.position = category.position,
        r.primary = category.primary
"""

def check_connection(driver):
    with driver.session(database=database) as session:
        result = session.run("RETURN 1")
        return result.single()[0] == 1

import uuid


def make_author_id(family_name: str, given_names: str) -> str:
    value = f"{family_name}-{given_names}".lower()
    clean_value = "".join(
        character for character in value if character.isalnum() or character == "-"
    )

    # Takes the first 8 characters of a fresh UUID v4
    short_uuid = str(uuid.uuid4())[:8]

    return f"{clean_value}-{short_uuid}"

def transform(record:dict)->dict:
    # Implement the transformation logic here
    authors = []

    for pos, author in enumerate(record.get("authors_parsed", []),start=1):
        family_name = author[0].strip()
        given_name = author[1].strip() if len(author) > 1 else ""
        authors.append({
            "author_id": make_author_id(family_name, given_name),
            "name": f"{given_name} {family_name}",
            "position": pos,
            "family_name": family_name,
            "given_name": given_name
        })
    categories = [
        {
            "code": code,
            "position": position,
            "primary": position == 1,
        }
        for position, code in enumerate(
            record.get("categories", "").split(),
            start=1,
        )
    ]

    return {
        "arxiv_id": record["id"],
        "title": record.get("title"),
        "abstract": record.get("abstract"),
        "update_date": record.get("update_date"),
        "authors": authors,
        "categories": categories,
    }

def main():
    driver = GraphDatabase.driver(uri, auth=(username, password))

    if check_connection(driver):
        print("Connection successful")
    else:
        print("Connection failed")

    try:
        with sample_path.open("r") as sample_file:
            for line in sample_file:
                # Load the record
                record = json.loads(line)

                # Process the record
                payload = transform(record)

                driver.execute_query(
                    QUERY,
                    parameters_=payload,
                    database_=database,
                )

                print(f"Loaded paper {payload['arxiv_id']}")
                
    except Exception as e:
        print(f"Error reading sample file: {e}")

    finally:
        driver.close()

if __name__ == "__main__":
    main()