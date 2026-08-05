import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def append_result(path: Path, record: dict[str, Any]) -> None:
    """Append one timestamped, git-tagged JSON record to a results log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        **record,
    }
    with path.open("a", encoding="utf-8") as results_file:
        results_file.write(json.dumps(entry) + "\n")
