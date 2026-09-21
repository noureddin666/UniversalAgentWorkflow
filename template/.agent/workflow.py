from __future__ import annotations

import sys
from pathlib import Path


vendor_root = Path(__file__).resolve().parent / "vendor" / "universal-agent-workflow"
sys.path.insert(0, str(vendor_root))

from tooling.workflow import main


if __name__ == "__main__":
    raise SystemExit(main())
