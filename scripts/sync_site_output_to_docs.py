from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site_output"
TARGET = ROOT / "docs"
PRESERVE_FILES = {
    "click_tracking_setup.md",
    "social_distribution_workflow.md",
}


def assert_inside_root(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    if not (resolved == root or root in resolved.parents):
        raise RuntimeError(f"Refusing to operate outside project root: {resolved}")
    return resolved


def sync_site_output_to_docs() -> dict[str, int]:
    source = assert_inside_root(SOURCE)
    target = assert_inside_root(TARGET)
    if not source.exists():
        raise FileNotFoundError(f"Missing source folder: {source}")
    if source == target:
        raise RuntimeError("Source and target folders must be different.")

    target.mkdir(parents=True, exist_ok=True)
    preserved: dict[str, str] = {}
    for name in PRESERVE_FILES:
        path = target / name
        if path.exists() and path.is_file():
            preserved[name] = path.read_text(encoding="utf-8")

    removed = 0
    copied = 0

    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1

    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
        copied += 1

    for name, content in preserved.items():
        (target / name).write_text(content, encoding="utf-8")

    return {"removed": removed, "copied": copied, "preserved": len(preserved)}


def main() -> None:
    result = sync_site_output_to_docs()
    print(
        "Synced site_output to docs: "
        f"removed={result['removed']} copied={result['copied']} preserved={result['preserved']}"
    )


if __name__ == "__main__":
    main()
