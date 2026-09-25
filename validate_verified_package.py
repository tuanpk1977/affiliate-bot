from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.verified_writer_package import validate_verified_package


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a self-contained verified external-writer package."
    )
    parser.add_argument("package", type=Path, help="Path to verified_package.zip or extracted folder.")
    args = parser.parse_args()
    result = validate_verified_package(args.package)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
