from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
import re

from modules.operational_health import PageParser


AI_STYLE = (
    "in today's fast-paced",
    "in the ever-evolving",
    "delve into",
    "game-changer",
    "revolutionize",
    "unlock the power",
    "it is important to note",
)
CTA_TERMS = ("try ", "visit ", "compare ", "read ", "check the official", "learn more")
USE_CASE_TERMS = ("use case", "best for", "who should use", "workflow")
PROS_CONS_TERMS = ("pros and cons", "advantages", "limitations", "drawbacks")
PRICING_TERMS = ("pricing", "price", "cost", "plan")
COMPARISON_TERMS = ("comparison", "alternatives", "versus", " vs ")


@dataclass
class ContentQAResult:
    file: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_sentence(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def inspect_content(path: Path, *, repair: bool = False) -> ContentQAResult:
    source = path.read_text(encoding="utf-8", errors="replace")
    parser = PageParser()
    parser.feed(source)
    result = ContentQAResult(file=str(path))
    paragraph_counts = Counter(normalize_sentence(value) for value in parser.paragraphs if len(value.split()) >= 12)
    repeats = [value for value, count in paragraph_counts.items() if count > 1]
    if repeats:
        result.errors.append(f"{len(repeats)} repetitive paragraph(s)")
        if repair:
            seen: set[str] = set()
            pattern = re.compile(r"<p\b[^>]*>.*?</p>", re.I | re.S)

            def dedupe(match: re.Match[str]) -> str:
                visible = unescape(re.sub(r"<[^>]+>", " ", match.group(0)))
                key = normalize_sentence(visible)
                if len(key.split()) < 12 or key not in paragraph_counts:
                    return match.group(0)
                if key in seen:
                    return ""
                seen.add(key)
                return match.group(0)

            updated = pattern.sub(dedupe, source)
            if updated != source:
                path.write_text(updated, encoding="utf-8")
                result.repaired.append("removed duplicate paragraphs")
                result.errors = [error for error in result.errors if "repetitive paragraph" not in error]
                source = updated
    lowered = source.casefold()
    style_hits = [phrase for phrase in AI_STYLE if phrase in lowered]
    if style_hits:
        result.warnings.append(f"AI-style wording: {', '.join(style_hits)}")
    headings = [(level, text) for level, text in parser.headings]
    heading_blob = " ".join(text for _, text in headings).casefold()
    heading_text = [normalize_sentence(text) for _, text in headings]
    duplicates = [text for text, count in Counter(heading_text).items() if count > 1]
    if duplicates:
        result.errors.append(f"{len(duplicates)} duplicated heading(s)")
    levels = [int(level[1]) for level, _ in headings]
    if any(current - previous > 1 for previous, current in zip(levels, levels[1:])):
        result.warnings.append("heading hierarchy skips a level")
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]+", " ".join(parser.paragraphs).casefold())
    if words:
        common_word, common_count = Counter(words).most_common(1)[0]
        if common_count / len(words) > 0.045 and common_word not in {"the", "and", "for", "with", "that", "this"}:
            result.warnings.append(f"possible keyword stuffing: {common_word}")
    if parser.paragraphs and len(parser.paragraphs[0].split()) < 35:
        result.warnings.append("weak or short introduction")
    if parser.paragraphs and len(parser.paragraphs[-1].split()) < 25:
        result.warnings.append("weak or short conclusion")
    if "FAQPage" not in source and "frequently asked questions" not in lowered:
        result.errors.append("missing FAQ")
    if not any(term in lowered for term in CTA_TERMS):
        result.errors.append("missing CTA")
    if not any(term in lowered for term in USE_CASE_TERMS):
        result.warnings.append("missing practical use-case section")
    if not any(term in lowered for term in PROS_CONS_TERMS):
        result.warnings.append("missing pros/cons or limitations section")
    if any(term in lowered for term in ("review", "software", "tool", "platform")) and not any(
        term in lowered for term in PRICING_TERMS
    ):
        result.warnings.append("missing pricing verification section")
    if any(term in lowered for term in ("alternatives", "comparison", " vs ")) and not any(
        term in heading_blob for term in COMPARISON_TERMS
    ):
        result.warnings.append("missing comparison section")
    anchors = re.findall(r"<a\b[^>]*>(.*?)</a>", source, re.I | re.S)
    unnatural = sum(
        normalize_sentence(re.sub(r"<[^>]+>", " ", anchor)) in {"click here", "here", "read more", "link"}
        for anchor in anchors
    )
    if unnatural:
        result.warnings.append(f"{unnatural} generic anchor text link(s)")
    return result


def write_content_qa_report(results: list[ContentQAResult], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Content QA Report", "", f"Status: **{'PASS' if all(item.ok for item in results) else 'FAIL'}**", ""]
    for result in results:
        lines.append(f"## {result.file}")
        lines.append(f"- Status: {'PASS' if result.ok else 'FAIL'}")
        lines.extend(f"- Error: {error}" for error in result.errors)
        lines.extend(f"- Warning: {warning}" for warning in result.warnings)
        lines.extend(f"- Repaired: {repair}" for repair in result.repaired)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
