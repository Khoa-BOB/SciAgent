"""Makes sciagent-KG's `queries` and `src` packages importable.

sciagent-KG has no build-system config (see specs/02-kg-service-architecture.md
§1) -- it's run in place via `uv run` from within that directory, not
installed as a library. Rather than restructure that project's packaging,
this adds its root to sys.path so this service can import its query builders
and retrieval classes directly, per the "wraps sciagent-KG as a library"
design in the architecture spec.

Import this before anything from `queries` or sciagent-KG's `src` package.
Do not add a top-level `src/` directory to this project -- sciagent-KG's own
top-level package is literally named `src`; two same-named packages on
sys.path at once resolve ambiguously.
"""

import sys
from pathlib import Path

SCIAGENT_KG_ROOT = Path(__file__).resolve().parents[2] / "sciagent-KG"

if not SCIAGENT_KG_ROOT.is_dir():
    raise RuntimeError(
        f"sciagent-KG not found at {SCIAGENT_KG_ROOT} -- expected as a sibling "
        "directory of sciagent-backend."
    )

if str(SCIAGENT_KG_ROOT) not in sys.path:
    sys.path.insert(0, str(SCIAGENT_KG_ROOT))
