from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import settings
from modules.affiliate_skills import run_skill
from modules.sitemap_generator import generate_sitemap
from modules.site_builder import page_shell


DRAFT_COLUMNS = [
    "draft_id",
    "created_at",
    "content_type",
    "target_channel",
    "title",
    "slug",
    "topic",
    "status",
    "draft_content",
    "target_url",
    "notes",
]

VALID_STATUSES = ["Draft", "Pending Review", "Need Edit", "Approved", "Rejected", "Published"]
WEBSITE_TYPES = {"Review page", "Comparison page", "FAQ page", "Blog article", "Website article"}


def ensure_content_drafts() -> pd.DataFrame:
    settings.content_drafts_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings.content_drafts_file.exists():
        df = pd.DataFrame(columns=DRAFT_COLUMNS)
        df.to_csv(settings.content_drafts_file, index=False)
        return df
    return load_drafts()


def load_drafts() -> pd.DataFrame:
    try:
        df = pd.read_csv(settings.content_drafts_file)
    except Exception:
        df = pd.DataFrame(columns=DRAFT_COLUMNS)
    for column in DRAFT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[DRAFT_COLUMNS].fillna("")
    if not df.empty:
        df["status"] = df["status"].apply(normalize_status)
    return df


def load_review_queue(import_affiliate_os: bool = True) -> pd.DataFrame:
    if import_affiliate_os:
        import_affiliate_os_drafts()
    return load_drafts()


def import_affiliate_os_drafts() -> pd.DataFrame:
    path = settings.data_dir / "affiliate_os_drafts.json"
    df = load_drafts()
    if not path.exists():
        return df
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return df
    existing_ids = set(df["draft_id"].astype(str)) if not df.empty else set()
    rows = []
    for idx, item in enumerate(raw, start=1):
        draft_id = f"OS-{idx:05d}"
        if draft_id in existing_ids:
            continue
        inputs = item.get("inputs", {}) if isinstance(item, dict) else {}
        output = str(item.get("output", "") if isinstance(item, dict) else "")
        title = extract_title(output) or str(inputs.get("main_keyword") or inputs.get("product_name") or f"Affiliate OS Draft {idx}")
        rows.append(
            {
                "draft_id": draft_id,
                "created_at": str(item.get("created_at", "")) if isinstance(item, dict) else "",
                "content_type": skill_to_content_type(str(item.get("command", "")) if isinstance(item, dict) else ""),
                "target_channel": "Affiliate OS",
                "title": title,
                "slug": slugify(title),
                "topic": str(inputs.get("main_keyword") or inputs.get("product_name") or title),
                "status": normalize_status(str(item.get("status", "Draft")) if isinstance(item, dict) else "Draft"),
                "draft_content": output,
                "target_url": "",
                "notes": "Imported from data/affiliate_os_drafts.json",
            }
        )
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        save_drafts(df)
    return df


def save_drafts(df: pd.DataFrame) -> pd.DataFrame:
    for column in DRAFT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[DRAFT_COLUMNS].fillna("")
    df.to_csv(settings.content_drafts_file, index=False)
    return df


def create_draft(
    content_type: str,
    target_channel: str,
    title: str,
    slug: str,
    topic: str,
    draft_content: str,
    status: str = "Pending Review",
    target_url: str = "",
    notes: str = "",
) -> dict[str, str]:
    df = load_drafts()
    record = {
        "draft_id": next_draft_id(df),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "content_type": content_type,
        "target_channel": target_channel,
        "title": title.strip() or topic.strip() or "Untitled draft",
        "slug": slugify(slug or title or topic),
        "topic": topic.strip(),
        "status": normalize_status(status) if normalize_status(status) in VALID_STATUSES else "Pending Review",
        "draft_content": draft_content.strip(),
        "target_url": target_url.strip(),
        "notes": notes.strip(),
    }
    df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    save_drafts(df)
    return record


def update_draft(draft_id: str, **updates: str) -> pd.DataFrame:
    df = load_drafts()
    mask = df["draft_id"].astype(str) == str(draft_id)
    if not mask.any():
        return df
    for key, value in updates.items():
        if key in DRAFT_COLUMNS:
            if key == "status":
                value = normalize_status(str(value))
            df.loc[mask, key] = value
    return save_drafts(df)


def approve_draft(draft_id: str, **updates: str) -> pd.DataFrame:
    return update_draft(draft_id, status="Approved", **updates)


def reject_draft(draft_id: str, **updates: str) -> pd.DataFrame:
    return update_draft(draft_id, status="Rejected", **updates)


def mark_need_edit(draft_id: str, **updates: str) -> pd.DataFrame:
    return update_draft(draft_id, status="Need Edit", **updates)


def save_draft(draft_id: str, **updates: str) -> pd.DataFrame:
    return update_draft(draft_id, **updates)


def generate_draft_content(topic: str, keyword: str, tool: str, content_type: str, audience: str, tone: str) -> str:
    tool = tool.strip() or topic.strip() or "the tool"
    inputs = {
        "product_name": tool,
        "main_keyword": keyword or f"{tool} review",
        "target_audience": audience or "người đang tìm hiểu AI/SaaS tools",
        "competitors": "main competitors",
        "content": f"Tone: {tone}. Topic: {topic}.",
    }
    if content_type in {"LinkedIn post", "Facebook post", "Medium article", "X thread", "Telegram post", "TikTok script"}:
        command = "/social" if content_type != "TikTok script" else "/video-script"
    elif content_type == "Review page":
        command = "/research"
    elif content_type == "Comparison page":
        command = "/research"
    elif content_type == "FAQ page":
        command = "/aeo-check"
    else:
        command = "/blog"
    result = run_skill(command, inputs)["output"]
    disclosure = "\n\nAffiliate disclosure: Some links may be affiliate links. We may earn a commission at no extra cost to you."
    cta = "\n\nCTA: Read the full review, verify official pricing, and compare alternatives before buying."
    return f"{result}{disclosure}{cta}"


def generate_multichannel_pack(topic: str, tool: str, keyword: str, audience: str = "", tone: str = "chuyên nghiệp") -> list[dict[str, str]]:
    content_types = [
        ("Website article", "Website"),
        ("LinkedIn post", "LinkedIn"),
        ("Facebook post", "Facebook"),
        ("Medium article", "Medium"),
        ("Telegram post", "Telegram"),
        ("X thread", "X/Twitter"),
        ("TikTok script", "TikTok"),
    ]
    records = []
    for content_type, channel in content_types:
        title = f"{topic} - {channel}"
        content = generate_draft_content(topic, keyword, tool, content_type, audience, tone)
        records.append(
            create_draft(
                content_type=content_type,
                target_channel=channel,
                title=title,
                slug=slugify(title),
                topic=topic,
                draft_content=content,
                status="Pending Review",
                notes="Generated as part of multichannel pack. Review before publishing.",
            )
        )
    return records


def generate_aeo_ideas(tool: str, use_case: str = "small business") -> list[dict[str, str]]:
    tool = tool.strip() or "AI tool"
    ideas = [
        f"{tool} vs competitors",
        f"Best AI tools for {use_case}",
        f"Alternatives to {tool}",
        f"Is {tool} worth it?",
        f"{tool} pricing explained",
        f"{tool} for beginners",
        f"{tool} vs top competitors",
    ]
    return [{"title": idea, "slug": slugify(idea), "topic": idea} for idea in ideas]


def generate_offpage_pack(draft: dict[str, str]) -> list[dict[str, str]]:
    topic = draft.get("topic") or draft.get("title") or "Approved website page"
    tool = extract_tool(topic)
    keyword = topic
    types = [
        ("LinkedIn post", "LinkedIn"),
        ("Facebook post", "Facebook"),
        ("Medium article", "Medium"),
        ("X thread", "X/Twitter"),
        ("Telegram post", "Telegram"),
        ("Reddit-style answer", "Reddit"),
        ("Quora-style answer", "Quora"),
        ("TikTok script", "TikTok"),
    ]
    records = []
    for content_type, channel in types:
        content = generate_draft_content(topic, keyword, tool, content_type, "người đang nghiên cứu công cụ", "chuyên nghiệp")
        records.append(
            create_draft(
                content_type=content_type,
                target_channel=channel,
                title=f"{topic} - {channel}",
                slug=slugify(f"{topic}-{channel}"),
                topic=topic,
                draft_content=content,
                status="Draft",
                notes=f"Off-page draft generated from approved page {draft.get('draft_id', '')}. Do not auto-post.",
            )
        )
    return records


def compliance_issues(content: str, title: str = "") -> list[str]:
    text = f"{title}\n{content}".lower()
    issues = []
    if "affiliate disclosure" not in text and "affiliate links" not in text:
        issues.append("Thiếu affiliate disclosure.")
    severe_phrases = ["guaranteed income", "100% success", "guaranteed roi", "easy money", "cam kết thu nhập"]
    for phrase in severe_phrases:
        if phrase in text:
            issues.append(f"SEVERE: Có claim rủi ro: {phrase}")
    if "i tested personally" in text and "placeholder" not in text:
        issues.append("Có claim 'I tested personally' nhưng chưa đánh dấu placeholder/xác minh.")
    if re.search(r"\b(best|top)\b(.{0,25})\b(best|top)\b(.{0,25})\b(best|top)\b", text):
        issues.append("Có dấu hiệu lặp keyword/spammy wording.")
    if "cta:" not in text and "visit official" not in text and "read the full" not in text:
        issues.append("CTA chưa rõ.")
    for brand in ["Canva", "Make", "Surfer SEO", "Webflow AI", "Copy.ai", "GitHub Copilot", "HubSpot", "Pipedrive", "ElevenLabs"]:
        if brand.lower() not in text and brand.split()[0].lower() in text:
            continue
    return issues


def can_approve(content: str, title: str = "") -> tuple[bool, list[str]]:
    issues = compliance_issues(content, title)
    severe = [issue for issue in issues if issue.startswith("SEVERE:")]
    return not severe, issues


def extract_review_parts(content: str) -> dict[str, str]:
    text = str(content or "")
    return {
        "seo_meta": extract_between(text, ["Meta title:", "Meta description:"], ["Intro:", "Sections:", "FAQ:"]),
        "faq": extract_between(text, ["FAQ:"], ["CTA:", "Internal links:", "Affiliate disclosure:"]),
        "cta": extract_between(text, ["CTA:"], ["Internal links:", "Affiliate disclosure:"]),
        "internal_links": extract_between(text, ["Internal links:"], ["Affiliate disclosure:", "Disclosure:"]),
        "affiliate_disclosure": extract_between(text, ["Affiliate disclosure:", "Disclosure:"], []),
    }


def publish_static_draft(draft_id: str, overwrite: bool = False) -> tuple[bool, str]:
    df = load_drafts()
    match = df[df["draft_id"].astype(str) == str(draft_id)]
    if match.empty:
        return False, "Không tìm thấy draft."
    row = match.iloc[0].to_dict()
    if row.get("status") != "Approved":
        return False, "Chỉ draft đã duyệt mới được xuất bản lên site static."
    if row.get("content_type") not in WEBSITE_TYPES:
        return False, "Chỉ Review page, Comparison page, FAQ page hoặc Blog article mới publish vào site static."
    slug = slugify(row.get("slug") or row.get("title"))
    guardrail_errors = publish_guardrail_errors(row, slug)
    if guardrail_errors:
        return False, "Publish blocked by quality guardrails: " + " | ".join(guardrail_errors)
    target_dir = settings.site_output_dir / slug
    target_file = target_dir / "index.html"
    if target_file.exists() and not overwrite:
        return False, f"Trang /{slug}/ đã tồn tại. Bật overwrite nếu muốn ghi đè."
    target_dir.mkdir(parents=True, exist_ok=True)
    body = draft_to_html_body(row)
    page = page_shell(
        str(row.get("title", "Draft")),
        f"Approved draft page for {row.get('topic', row.get('title', 'AI/SaaS research'))}.",
        body,
        f"/{slug}/",
    )
    target_file.write_text(page, encoding="utf-8")
    archive_dir = settings.data_dir / "published_static_pages" / slug
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "index.html").write_text(page, encoding="utf-8")
    url = f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/{slug}/"
    update_draft(draft_id, status="Published", target_url=url, notes=f"{row.get('notes', '')} | Published at {datetime.now().isoformat(timespec='seconds')}")
    update_static_indexes(slug, row.get("title", slug), url)
    return True, url


def publish_static_page(draft_id: str, overwrite: bool = False) -> tuple[bool, str]:
    return publish_static_draft(draft_id, overwrite=overwrite)


def publish_static_draft(draft_id: str, overwrite: bool = False) -> tuple[bool, str]:
    """Publish an approved website draft into site_output and the durable archive.

    Human approval is the hard gate. Quality guardrails still run, but older
    short drafts are published with warnings instead of silently staying 404.
    """
    df = load_drafts()
    match = df[df["draft_id"].astype(str) == str(draft_id)]
    if match.empty:
        return False, "Draft not found."
    row = match.iloc[0].to_dict()
    if row.get("status") not in {"Approved", "Published"}:
        return False, "Only Approved or Published drafts can be published to the static site."
    if row.get("content_type") not in WEBSITE_TYPES:
        return False, "Only Review page, Comparison page, FAQ page, Blog article, or Website article can be published."

    slug = slugify(row.get("slug") or row.get("title"))
    warnings = publish_guardrail_warnings(row, slug)
    blocking = blocking_publish_errors(warnings)
    if blocking:
        return False, "Publish blocked: " + " | ".join(blocking)

    target_dir = settings.site_output_dir / slug
    target_file = target_dir / "index.html"
    if target_file.exists() and not overwrite:
        return False, f"Page /{slug}/ already exists. Enable overwrite if you want to replace it."

    target_dir.mkdir(parents=True, exist_ok=True)
    body = draft_to_html_body(row)
    page = page_shell(
        str(row.get("title", "Draft")),
        f"Approved draft page for {row.get('topic', row.get('title', 'AI/SaaS research'))}.",
        body,
        f"/{slug}/",
    )
    target_file.write_text(page, encoding="utf-8")

    archive_dir = settings.data_dir / "published_static_pages" / slug
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "index.html").write_text(page, encoding="utf-8")

    url = f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/{slug}/"
    warning_note = ""
    if warnings:
        warning_note = " | Publish warnings: " + ", ".join(warnings)
    update_draft(
        draft_id,
        status="Published",
        target_url=url,
        notes=f"{row.get('notes', '')} | Published at {datetime.now().isoformat(timespec='seconds')}{warning_note}",
    )
    update_static_indexes(slug, row.get("title", slug), url)
    sync_social_posts_for_published_url(slug, url)
    return True, url


def publish_static_page(draft_id: str, overwrite: bool = False) -> tuple[bool, str]:
    return publish_static_draft(draft_id, overwrite=overwrite)


def draft_to_html_body(row: dict[str, str]) -> str:
    title = html.escape(str(row.get("title", "")))
    normalized_content = normalize_draft_content_links(str(row.get("draft_content", "")))
    content = html.escape(normalized_content).replace("\n", "<br>")
    return f"""<article class="card">
<h1>{title}</h1>
<p class="muted">Approved human-reviewed draft. Last updated {datetime.now().date().isoformat()}.</p>
<section><h2>Content</h2><p>{content}</p></section>
<section class="trust"><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></section>
<section><h2>Next step</h2><p><a class="btn" href="/reviews/">Read related reviews</a><a class="btn secondary" href="/comparisons/">Compare tools</a></p></section>
</article>"""


def update_static_indexes(slug: str, title: str, url: str) -> None:
    generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    llms = settings.site_output_dir / "llms.txt"
    if llms.exists():
        text = llms.read_text(encoding="utf-8")
        line = f"- {title}: {url}"
        if url not in text:
            llms.write_text(text.rstrip() + "\n\nApproved human-published pages:\n" + line + "\n", encoding="utf-8")
    add_published_link_to_index(slug, title)


def sync_social_posts_for_published_url(slug: str, url: str) -> None:
    report = settings.data_dir / "social_post_report.csv"
    if not report.exists():
        return
    try:
        df = pd.read_csv(report).fillna("")
    except Exception:
        return
    if "article_slug" not in df.columns or "article_url" not in df.columns:
        return
    mask = df["article_slug"].astype(str) == str(slug)
    if not mask.any():
        return
    old_urls = set(df.loc[mask, "article_url"].astype(str).tolist())
    df.loc[mask, "article_url"] = url
    df.to_csv(report, index=False)
    if "output_path" not in df.columns:
        return
    for output in df.loc[mask, "output_path"].astype(str).tolist():
        path = Path(output)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for old_url in old_urls:
            if old_url:
                text = text.replace(old_url, url)
        path.write_text(text, encoding="utf-8")


def add_published_link_to_index(slug: str, title: str) -> None:
    is_comparison = " vs " in str(title).lower() or "-vs-" in slug
    index_dir = "comparisons" if is_comparison else "reviews"
    index_file = settings.site_output_dir / index_dir / "index.html"
    if not index_file.exists():
        return
    text = index_file.read_text(encoding="utf-8", errors="ignore")
    if f'href="/{slug}/"' in text or f"href='/{slug}/'" in text:
        return
    block_title = "Approved comparison drafts" if is_comparison else "Approved review drafts"
    block = (
        f"\n<section class=\"approved-drafts\" data-approved-drafts=\"{index_dir}\">"
        f"<h2>{html.escape(block_title)}</h2>"
        f"<p>Human-approved static pages published from the local review workflow.</p>"
        f"<ul><li><a href=\"/{slug}/\">{html.escape(str(title or slug))}</a></li></ul>"
        f"</section>\n"
    )
    if "</main>" in text:
        text = text.replace("</main>", block + "</main>", 1)
    elif "<footer" in text:
        text = text.replace("<footer", block + "<footer", 1)
    else:
        text += block
    index_file.write_text(text, encoding="utf-8")


def publish_guardrail_errors(row: dict[str, str], slug: str) -> list[str]:
    content = str(row.get("draft_content", "") or "")
    title = str(row.get("title", "") or "")
    errors: list[str] = []
    if not draft_screenshot_exists(slug):
        errors.append("missing_screenshot")
    if draft_word_count(content) < 1200:
        errors.append("word_count_under_1200")
    if not re.search(r"/go/|CTA:|Visit Official|Check current pricing|Read review", content, flags=re.IGNORECASE):
        errors.append("missing_cta")
    internal_links = draft_internal_links(content)
    if len(internal_links) < 3:
        errors.append("internal_links_under_3")
    if re.search(r"\blorem\b|\btodo\b|your api key|example\.com|affiliate link here", content, flags=re.IGNORECASE):
        errors.append("placeholder_text")
    if not title.strip():
        errors.append("missing_title")
    if has_broken_draft_links(internal_links):
        errors.append("broken_internal_link")
    return errors


def publish_guardrail_warnings(row: dict[str, str], slug: str) -> list[str]:
    return publish_guardrail_errors(row, slug)


def blocking_publish_errors(warnings: list[str]) -> list[str]:
    blocking = {"placeholder_text", "missing_title", "broken_internal_link"}
    return [item for item in warnings if item in blocking]


def draft_screenshot_exists(slug: str) -> bool:
    aliases = {
        "cursor-ai-review-a-practical-guide-for-developers-and-ai-coders": "cursor",
        "windsurf-review": "windsurf",
    }
    image_slug = aliases.get(slug, slug)
    return (settings.base_dir / "assets" / "screenshots" / f"{image_slug}.png").exists()


def draft_word_count(content: str) -> int:
    visible = re.sub(r"<[^>]+>", " ", str(content or ""))
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", visible))


def draft_internal_links(content: str) -> set[str]:
    return set(re.findall(r"(?<!:)(/[a-z0-9][a-z0-9\-/]+/)", str(content or ""), flags=re.IGNORECASE))


def has_broken_draft_links(links: set[str]) -> bool:
    for link in links:
        if link.startswith(("/go/", "/assets/")):
            continue
        resolved = resolve_draft_link(link)
        if not (settings.site_output_dir / resolved.strip("/") / "index.html").exists():
            return True
    return False


def normalize_draft_content_links(content: str) -> str:
    text = str(content or "")
    for link in sorted(draft_internal_links(text), key=len, reverse=True):
        resolved = resolve_draft_link(link)
        if resolved != link:
            text = text.replace(link, resolved)
    return text


def resolve_draft_link(link: str) -> str:
    clean = "/" + str(link or "").strip("/") + "/"
    if (settings.site_output_dir / clean.strip("/") / "index.html").exists():
        return clean
    alias_map = {
        "/cursor-ai/": "/review/cursor/",
        "/github-copilot-ai/": "/review/github-copilot/",
        "/copilot-ai/": "/review/github-copilot/",
        "/windsurf-ai/": "/windsurf-review/",
    }
    if clean in alias_map and (settings.site_output_dir / alias_map[clean].strip("/") / "index.html").exists():
        return alias_map[clean]
    if clean.endswith("-ai/"):
        base_slug = clean.strip("/")[:-3]
        candidates = [f"/review/{base_slug}/", f"/{base_slug}/"]
        for candidate in candidates:
            if (settings.site_output_dir / candidate.strip("/") / "index.html").exists():
                return candidate
    return clean


def export_markdown(row: dict[str, str]) -> str:
    return f"# {row.get('title', '')}\n\n{row.get('draft_content', '')}\n\n---\nAffiliate disclosure: Some links may be affiliate links. We may earn a commission at no extra cost to you.\n"


def export_html(row: dict[str, str]) -> str:
    return draft_to_html_body(row)


def next_draft_id(df: pd.DataFrame) -> str:
    return f"DRAFT-{len(df) + 1:05d}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "draft"


def extract_tool(topic: str) -> str:
    return str(topic).split(" vs ")[0].split(":")[0].strip() or "AI tool"


def normalize_status(status: str) -> str:
    value = str(status or "").strip()
    mapping = {
        "Draft": "Need Edit",
        "Needs Edit": "Need Edit",
        "Need edit": "Need Edit",
        "Cần chỉnh sửa": "Need Edit",
        "Đang chờ duyệt": "Pending Review",
        "Đã duyệt": "Approved",
        "Từ chối": "Rejected",
        "Đã đăng": "Published",
    }
    return mapping.get(value, value if value in VALID_STATUSES else "Pending Review")


def extract_title(output: str) -> str:
    for line in str(output or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip()
        if stripped and len(stripped) < 120:
            return stripped.replace("#", "").strip()
    return ""


def skill_to_content_type(command: str) -> str:
    mapping = {
        "/blog": "Blog article",
        "/landing": "Review page",
        "/social": "Social post",
        "/video-script": "TikTok script",
        "/repurpose": "Multichannel pack",
        "/research": "Review page",
        "/aeo-check": "FAQ page",
    }
    return mapping.get(command, "Affiliate OS draft")


def extract_between(text: str, starts: list[str], ends: list[str]) -> str:
    lower = text.lower()
    start_pos = -1
    start_token = ""
    for token in starts:
        pos = lower.find(token.lower())
        if pos != -1 and (start_pos == -1 or pos < start_pos):
            start_pos = pos
            start_token = token
    if start_pos == -1:
        return ""
    start = start_pos + len(start_token)
    end_candidates = [lower.find(token.lower(), start) for token in ends if lower.find(token.lower(), start) != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()
