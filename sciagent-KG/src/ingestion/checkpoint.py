import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

CHECKPOINT_DIR = Path(__file__).parents[2] / ".checkpoints"


@dataclass
class Checkpoint:
    last_line: int
    last_arxiv_id: str


def checkpoint_path_for(metadata_path: Path) -> Path:
    """One checkpoint file per input file, keyed by its resolved absolute path."""
    digest = hashlib.sha256(str(metadata_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return CHECKPOINT_DIR / f"{metadata_path.name}.{digest}.json"


def load_checkpoint(metadata_path: Path) -> Checkpoint | None:
    """Return the checkpoint for metadata_path, or None if missing or stale.

    Staleness is detected via source file size: if the file has been edited
    since the checkpoint was written, the recorded line number no longer
    means anything, so we discard it rather than skip the wrong lines.
    """
    path = checkpoint_path_for(metadata_path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if data.get("source_size") != metadata_path.stat().st_size:
        return None

    return Checkpoint(
        last_line=data["last_line"],
        last_arxiv_id=data["last_arxiv_id"],
    )


def save_checkpoint(metadata_path: Path, last_line: int, last_arxiv_id: str) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = checkpoint_path_for(metadata_path)
    path.write_text(
        json.dumps(
            {
                "source_path": str(metadata_path.resolve()),
                "source_size": metadata_path.stat().st_size,
                "last_line": last_line,
                "last_arxiv_id": last_arxiv_id,
            }
        ),
        encoding="utf-8",
    )


def reset_checkpoint(metadata_path: Path) -> None:
    checkpoint_path_for(metadata_path).unlink(missing_ok=True)
