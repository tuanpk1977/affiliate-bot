from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
    )


def extract(pattern: str, source: str) -> str | None:
    match = re.search(pattern, source, flags=re.I | re.S)
    return match.group(2) if match else None


def replace(pattern: str, source: str, value: str) -> str:
    return re.sub(pattern, rf"\g<1>{value}\g<3>", source, count=1, flags=re.I | re.S)


def main() -> None:
    staged = 0
    for page in sorted(DOCS.rglob("*.html")):
        rel = page.relative_to(ROOT).as_posix()
        try:
            original_bytes = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
        except subprocess.CalledProcessError:
            continue
        original = original_bytes.decode("utf-8", errors="strict")
        current = page.read_bytes().decode("utf-8", errors="strict")
        updated = original

        patterns = (
            r"(<title\b[^>]*>)(.*?)(</title>)",
            r"(<meta\b(?=[^>]*(?:property|name)=['\"]og:title['\"])[^>]*\bcontent=['\"])([^'\"]*)(['\"][^>]*>)",
            r"(<meta\b(?=[^>]*(?:property|name)=['\"]twitter:title['\"])[^>]*\bcontent=['\"])([^'\"]*)(['\"][^>]*>)",
        )
        for pattern in patterns:
            value = extract(pattern, current)
            if value is not None:
                updated = replace(pattern, updated, value)
        if updated == original:
            continue

        mode_line = git("ls-files", "-s", "--", rel).strip()
        mode = mode_line.split()[0] if mode_line else "100644"
        blob = subprocess.check_output(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=ROOT,
            input=updated.encode("utf-8"),
        ).decode("ascii").strip()
        subprocess.check_call(["git", "update-index", "--cacheinfo", f"{mode},{blob},{rel}"], cwd=ROOT)
        staged += 1
    print(f"staged_title_only_files={staged}")


if __name__ == "__main__":
    main()
