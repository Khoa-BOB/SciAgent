import json
from pathlib import Path
print(Path.cwd())
input_path = Path("data/arxiv/arxiv-metadata-oai-snapshot.json")
output_path = Path("data/csAI/cs_ai_papers.jsonl")

count = 0

with input_path.open("r", encoding="utf-8") as infile, \
     output_path.open("w", encoding="utf-8") as outfile:

    for line_number, line in enumerate(infile, start=1):
        try:
            paper = json.loads(line)
        except json.JSONDecodeError:
            print(f"Skipping invalid JSON on line {line_number}")
            continue

        categories = paper.get("categories", "").split()

        if "cs.AI" in categories:
            outfile.write(json.dumps(paper, ensure_ascii=False) + "\n")
            count += 1

print(f"Saved {count:,} cs.AI papers to {output_path}")