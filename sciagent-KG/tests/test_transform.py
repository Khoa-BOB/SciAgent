import json
from pathlib import Path

from src.transform import transform


SAMPLE = Path(__file__).parents[2] / "data/example/example.jsonl"


def test_transform_maps_all_metadata_and_is_idempotent():
    with SAMPLE.open(encoding="utf-8") as sample_file:
        record = json.loads(next(sample_file))

    payload = transform(record)

    assert payload["arxiv_id"] == "0704.0047"
    assert payload["comments"] == "5 pages, 5 eps figures, uses IEEEtran.cls"
    assert payload["doi"] is None
    assert payload["license"] is None
    assert payload["source"] == "arXiv"
    assert payload["submitter"]["name"] == "Igor Grabec"
    assert payload["versions"] == [
        {
            "version_id": "0704.0047-v1",
            "version_number": 1,
            "label": "v1",
            "created_at": "2007-04-01T13:06:50+00:00",
        }
    ]
    assert payload["latest_version"] == "v1"
    assert payload["version_count"] == 1
    assert payload["categories"][0]["primary"] is True
    assert payload["authors"][0]["given_names"] == "T."

    # MERGE keys must not change between runs.
    assert transform(record)["authors"][0]["author_id"] == (
        payload["authors"][0]["author_id"]
    )


def test_transform_maps_optional_publication_metadata():
    record = {
        "id": "0704.0001",
        "journal-ref": "Phys.Rev.D76:013009,2007",
        "doi": "10.1103/PhysRevD.76.013009",
        "report-no": "ANL-HEP-PR-07-12",
    }

    payload = transform(record)

    assert payload["doi"] == "10.1103/PhysRevD.76.013009"
    assert payload["journal"]["journal_reference_raw"] == (
        "Phys.Rev.D76:013009,2007"
    )
    assert payload["report"] == {"report_number": "ANL-HEP-PR-07-12"}
