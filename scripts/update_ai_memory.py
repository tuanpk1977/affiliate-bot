from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_intelligence import write_ai_memory


def main() -> int:
    rows = write_ai_memory()
    print(f"AI memory rows: {len(rows)}")
    print("Output: data/ai_memory.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
