from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PINTEREST_DOMAIN_VERIFY = "4fec8bab7309c27bc57a5d499b40cf9b"
PINTEREST_META_TAG = f'<meta name="p:domain_verify" content="{PINTEREST_DOMAIN_VERIFY}"/>'

_PINTEREST_META_RE = re.compile(
    r"<meta\b(?=[^>]*\bname\s*=\s*(['\"])p:domain_verify\1)[^>]*>",
    flags=re.IGNORECASE,
)
_CHARSET_META_RE = re.compile(r"<meta\b[^>]*\bcharset\s*=\s*(['\"])?utf-8\1?[^>]*>", flags=re.IGNORECASE)
_HEAD_RE = re.compile(r"<head\b[^>]*>", flags=re.IGNORECASE)


def inject_pinterest_domain_verification(html_text: str) -> tuple[str, bool]:
    """Return HTML containing exactly one current Pinterest domain-verification tag."""
    existing = list(_PINTEREST_META_RE.finditer(html_text))
    if existing:
        if len(existing) == 1 and existing[0].group(0) == PINTEREST_META_TAG:
            return html_text, False
        first = existing[0]
        tail = _PINTEREST_META_RE.sub("", html_text[first.end() :])
        return html_text[: first.start()] + PINTEREST_META_TAG + tail, True

    charset = _CHARSET_META_RE.search(html_text)
    if charset:
        insertion = charset.end()
        return html_text[:insertion] + "\n  " + PINTEREST_META_TAG + html_text[insertion:], True

    head = _HEAD_RE.search(html_text)
    if not head:
        return html_text, False
    insertion = head.end()
    return html_text[:insertion] + "\n  " + PINTEREST_META_TAG + html_text[insertion:], True


def apply_pinterest_domain_verification(root: Path, *, files: list[Path] | None = None) -> dict[str, int]:
    candidates = files if files is not None else sorted(root.rglob("*.html"))
    stats = {"scanned": 0, "changed": 0, "already_present": 0, "missing_head": 0}
    for path in candidates:
        if not path.is_file():
            continue
        stats["scanned"] += 1
        source = path.read_text(encoding="utf-8", errors="strict")
        updated, changed = inject_pinterest_domain_verification(source)
        if changed:
            path.write_text(updated, encoding="utf-8")
            stats["changed"] += 1
        elif _PINTEREST_META_RE.search(source):
            stats["already_present"] += 1
        else:
            stats["missing_head"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply shared Pinterest domain verification metadata to static HTML output.")
    parser.add_argument("--root", action="append", required=True, help="Static HTML root to update. May be repeated.")
    args = parser.parse_args(argv)
    results: dict[str, dict[str, int]] = {}
    for value in args.root:
        root = Path(value).resolve()
        if not root.exists() or not root.is_dir():
            parser.error(f"HTML root does not exist: {root}")
        results[str(root)] = apply_pinterest_domain_verification(root)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
