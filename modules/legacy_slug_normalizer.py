from __future__ import annotations

from pathlib import Path


LEGACY_SLUG_REPLACEMENTS = {
    "ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflow/": "ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflows/",
}


def normalize_legacy_slugs(output_dir: Path) -> dict[str, int]:
    changed = 0
    replacements = 0
    for page in output_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="ignore")
        updated = text
        for old, new in LEGACY_SLUG_REPLACEMENTS.items():
            count = updated.count(old)
            if count:
                updated = updated.replace(old, new)
                replacements += count
        if updated != text:
            page.write_text(updated, encoding="utf-8")
            changed += 1
    return {"changed": changed, "replacements": replacements}
