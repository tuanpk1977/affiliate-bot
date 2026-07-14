from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from modules.site_verification_meta import (
    PINTEREST_META_TAG,
    apply_pinterest_domain_verification,
    inject_pinterest_domain_verification,
)


def test_injects_pinterest_meta_after_charset_and_is_idempotent() -> None:
    source = '<!doctype html><html><head><meta charset="utf-8"><title>Page</title></head><body></body></html>'

    updated, changed = inject_pinterest_domain_verification(source)
    second, changed_again = inject_pinterest_domain_verification(updated)

    assert changed is True
    assert changed_again is False
    assert second == updated
    assert updated.count('name="p:domain_verify"') == 1
    assert updated.index(PINTEREST_META_TAG) < updated.index("<title>")


def test_replaces_existing_wrong_value_without_duplicate() -> None:
    source = (
        '<html><head><meta name="p:domain_verify" content="old">'
        '<meta name="p:domain_verify" content="duplicate"></head><body></body></html>'
    )

    updated, changed = inject_pinterest_domain_verification(source)

    assert changed is True
    assert updated.count('name="p:domain_verify"') == 1
    assert PINTEREST_META_TAG in updated
    assert 'content="old"' not in updated


def test_processes_every_html_page_but_leaves_non_html_unchanged() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pages = [root / "index.html", root / "about" / "index.html", root / "vi" / "index.html"]
        for page in pages:
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text('<html><head><meta charset="utf-8"></head><body>Page</body></html>', encoding="utf-8")
        text_file = root / "robots.txt"
        text_file.write_text("User-agent: *", encoding="utf-8")

        first = apply_pinterest_domain_verification(root)
        second = apply_pinterest_domain_verification(root)

        assert first == {"scanned": 3, "changed": 3, "already_present": 0, "missing_head": 0}
        assert second == {"scanned": 3, "changed": 0, "already_present": 3, "missing_head": 0}
        assert all(PINTEREST_META_TAG in page.read_text(encoding="utf-8") for page in pages)
        assert text_file.read_text(encoding="utf-8") == "User-agent: *"
