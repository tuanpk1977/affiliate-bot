from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from config import settings


COMMUNITY_COLUMNS = [
    "community_id",
    "platform",
    "community_name",
    "community_url",
    "language",
    "topic_category",
    "audience_type",
    "member_count",
    "recent_activity_score",
    "engagement_score",
    "ai_interest_score",
    "link_allowed",
    "posting_rules_summary",
    "spam_risk",
    "join_priority",
    "recommended_action",
    "suggested_angle",
    "notes",
    "status",
]

POST_COLUMNS = [
    "post_id",
    "platform",
    "community_id",
    "community_name",
    "language",
    "source_url",
    "tracked_url",
    "content_variant",
    "content_style",
    "content",
    "cta",
    "hashtags",
    "estimated_risk",
    "status",
    "schedule_time",
    "notes",
]

JOIN_CHECKLIST_COLUMNS = [
    "community_id",
    "platform",
    "community_name",
    "community_url",
    "join_priority",
    "recommended_action",
    "check_rules",
    "check_link_policy",
    "introduce_without_link",
    "status",
    "notes",
]

PERFORMANCE_COLUMNS = [
    "platform",
    "community_id",
    "community_name",
    "posts_created",
    "published_posts",
    "clicks",
    "impressions",
    "ctr",
    "recommendation",
]

ACTION_LOG_COLUMNS = ["timestamp", "actor", "action", "object_type", "object_id", "status", "notes"]

VI_SEEDS = [
    "ChatGPT Việt Nam",
    "AI Việt Nam",
    "Trí tuệ nhân tạo Việt Nam",
    "Cộng đồng AI",
    "Công cụ AI",
    "AI tools Việt Nam",
    "Digital Marketing Việt Nam",
    "SEO Việt Nam",
    "Affiliate Marketing Việt Nam",
    "MMO Việt Nam",
    "Lập trình viên Việt Nam",
    "No-code Việt Nam",
    "Automation Việt Nam",
    "Startup Việt Nam",
    "SaaS Việt Nam",
    "Freelancer Việt Nam",
    "Cursor AI",
    "Windsurf AI",
    "GitHub Copilot",
    "Codex",
]

EN_SEEDS = [
    "AI tools",
    "Generative AI",
    "ChatGPT",
    "AI coding",
    "Cursor AI",
    "Windsurf AI",
    "GitHub Copilot",
    "Codex",
    "Developer tools",
    "SaaS growth",
    "SEO tools",
    "Affiliate marketing",
    "Marketing automation",
    "No-code automation",
    "Build in public",
    "Startup founders",
    "Indie hackers",
]

FIRST_CAMPAIGN_PAGES = [
    "/best-ai-coding-tools-2026/",
    "/blog/chatgpt-windsurf-codex-workflow/",
    "/blog/chatgpt-prompts-for-windsurf/",
    "/blog/windsurf-prompt-checklist/",
    "/blog/windsurf-to-codex-workflow/",
    "/comparisons/cursor-vs-windsurf/",
    "/comparisons/copilot-vs-cursor/",
    "/comparisons/synthesia-vs-runway/",
]

DEFAULT_REVIEW_WINDOWS = ["09:00", "20:00"]


@dataclass(frozen=True)
class DiscoverySeed:
    platform: str
    seed: str
    language: str


def community_recommendations_path() -> Path:
    return settings.data_dir / "community_recommendations.csv"


def community_posts_path() -> Path:
    return settings.data_dir / "community_post_drafts.csv"


def join_checklist_path() -> Path:
    return settings.data_dir / "community_join_checklist.csv"


def community_report_path() -> Path:
    return settings.data_dir / "community_discovery_report.csv"


def performance_report_path() -> Path:
    return settings.data_dir / "community_performance_report.csv"


def action_log_path() -> Path:
    return settings.data_dir / "community_action_log.csv"


def config_path() -> Path:
    return settings.base_dir / "config" / "community_discovery.json"


def ensure_community_discovery_assets() -> dict[str, int]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_config()
    communities = merge_with_existing_status(generate_community_recommendations(), community_recommendations_path(), "community_id")
    write_csv(community_recommendations_path(), communities, COMMUNITY_COLUMNS)
    posts = merge_with_existing_status(generate_group_post_drafts(communities), community_posts_path(), "post_id")
    write_csv(community_posts_path(), posts, POST_COLUMNS)
    checklist = generate_join_checklist(communities)
    write_csv(join_checklist_path(), checklist, JOIN_CHECKLIST_COLUMNS)
    performance = generate_performance_report(communities, posts)
    write_csv(performance_report_path(), performance, PERFORMANCE_COLUMNS)
    summary = generate_discovery_report(communities, posts)
    write_csv(community_report_path(), summary, ["metric", "value"])
    ensure_action_log()
    return {
        "communities": len(communities),
        "recommended": sum(1 for row in communities if row["status"] in {"recommended", "joined"}),
        "drafts": len(posts),
        "pending_review": sum(1 for row in posts if row["status"] == "pending_review"),
        "invalid_x_posts": count_invalid_x_posts(posts),
    }


def ensure_config() -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    payload = {
        "enabled": True,
        "auto_join_enabled": False,
        "auto_post_external_groups": False,
        "review_windows": DEFAULT_REVIEW_WINDOWS,
        "owned_channels_auto_publish": False,
        "max_groups_per_campaign": 6,
        "max_posts_per_group": 6,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_community_recommendations() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seeds = discovery_seeds()
    for item in seeds:
        rows.append(build_community_row(item))
    rows.sort(key=lambda row: (priority_sort(row["join_priority"]), -int(row["ai_interest_score"]), row["platform"], row["community_name"]))
    return rows


def discovery_seeds() -> list[DiscoverySeed]:
    platforms = ["Facebook Groups", "LinkedIn Groups/Pages", "X/Twitter", "Telegram", "Reddit", "Quora"]
    rows: list[DiscoverySeed] = []
    for seed in VI_SEEDS:
        for platform in platforms[:4]:
            rows.append(DiscoverySeed(platform=platform, seed=seed, language="vi"))
    for seed in EN_SEEDS:
        for platform in platforms:
            rows.append(DiscoverySeed(platform=platform, seed=seed, language="en"))
    return rows


def build_community_row(item: DiscoverySeed) -> dict[str, str]:
    community_id = stable_id(item.platform, item.seed, item.language)
    topic = topic_category(item.seed)
    audience = audience_type(item.seed)
    activity = activity_score(item.platform, item.seed)
    engagement = engagement_score(item.platform, item.seed)
    ai_interest = ai_interest_score(item.seed)
    link_allowed = link_policy(item.platform)
    spam = spam_risk(item.platform, item.seed, link_allowed)
    score = community_score(topic, activity, engagement, ai_interest, link_allowed, audience, spam)
    priority = priority_from_score(score)
    action = recommended_action(priority, link_allowed, spam)
    status = "recommended" if priority in {"A", "B"} else "discovered"
    return {
        "community_id": community_id,
        "platform": item.platform,
        "community_name": community_name(item),
        "community_url": community_search_url(item.platform, item.seed),
        "language": item.language,
        "topic_category": topic,
        "audience_type": audience,
        "member_count": "",
        "recent_activity_score": str(activity),
        "engagement_score": str(engagement),
        "ai_interest_score": str(ai_interest),
        "link_allowed": link_allowed,
        "posting_rules_summary": posting_rules_summary(item.platform, link_allowed),
        "spam_risk": spam,
        "join_priority": priority,
        "recommended_action": action,
        "suggested_angle": suggested_angle(topic, audience, item.language),
        "notes": "Local discovery target. Verify group rules manually before joining or posting.",
        "status": status,
    }


def community_name(item: DiscoverySeed) -> str:
    suffix = {
        "Facebook Groups": "Facebook group search",
        "LinkedIn Groups/Pages": "LinkedIn community search",
        "X/Twitter": "X hashtag/account search",
        "Telegram": "Telegram channel/group search",
        "Reddit": "Reddit subreddit search",
        "Quora": "Quora space/topic search",
    }.get(item.platform, "community search")
    return f"{item.seed} - {suffix}"


def community_search_url(platform: str, seed: str) -> str:
    q = urlencode({"q": seed})
    if platform == "Facebook Groups":
        return f"https://www.facebook.com/search/groups/?{q}"
    if platform == "LinkedIn Groups/Pages":
        return f"https://www.linkedin.com/search/results/groups/?{q}"
    if platform == "X/Twitter":
        return f"https://x.com/search?{urlencode({'q': seed, 'src': 'typed_query'})}"
    if platform == "Telegram":
        return f"https://t.me/s/{seed.replace(' ', '')}"
    if platform == "Reddit":
        return f"https://www.reddit.com/search/?{q}&type=sr"
    if platform == "Quora":
        return f"https://www.quora.com/search?{q}"
    return ""


def topic_category(seed: str) -> str:
    text = seed.lower()
    if any(term in text for term in ["cursor", "windsurf", "copilot", "codex", "coding", "lập trình", "developer"]):
        return "ai_coding_tools"
    if any(term in text for term in ["seo"]):
        return "seo"
    if any(term in text for term in ["affiliate", "mmo"]):
        return "affiliate"
    if any(term in text for term in ["automation", "no-code", "no code"]):
        return "automation"
    if any(term in text for term in ["startup", "saas", "founder", "indie"]):
        return "startup_saas"
    if any(term in text for term in ["marketing"]):
        return "marketing"
    return "general_ai"


def audience_type(seed: str) -> str:
    text = seed.lower()
    if any(term in text for term in ["coding", "cursor", "windsurf", "copilot", "codex", "developer", "lập trình"]):
        return "developers"
    if any(term in text for term in ["marketing", "seo"]):
        return "marketers"
    if any(term in text for term in ["affiliate", "mmo"]):
        return "affiliate"
    if any(term in text for term in ["freelancer"]):
        return "freelancers"
    if any(term in text for term in ["startup", "founder", "indie", "saas"]):
        return "founders"
    return "general_ai"


def activity_score(platform: str, seed: str) -> int:
    base = {"Facebook Groups": 14, "LinkedIn Groups/Pages": 12, "X/Twitter": 18, "Telegram": 13, "Reddit": 15, "Quora": 9}.get(platform, 10)
    if topic_category(seed) in {"ai_coding_tools", "general_ai"}:
        base += 4
    return min(base, 20)


def engagement_score(platform: str, seed: str) -> int:
    base = {"Facebook Groups": 14, "LinkedIn Groups/Pages": 15, "X/Twitter": 13, "Telegram": 11, "Reddit": 16, "Quora": 10}.get(platform, 10)
    if audience_type(seed) in {"developers", "founders"}:
        base += 3
    return min(base, 20)


def ai_interest_score(seed: str) -> int:
    if topic_category(seed) == "ai_coding_tools":
        return 30
    if "ai" in seed.lower() or "chatgpt" in seed.lower():
        return 27
    if topic_category(seed) in {"automation", "seo", "startup_saas"}:
        return 22
    return 18


def link_policy(platform: str) -> str:
    if platform in {"Telegram", "X/Twitter"}:
        return "yes"
    if platform in {"Facebook Groups", "LinkedIn Groups/Pages", "Reddit", "Quora"}:
        return "unknown"
    return "unknown"


def spam_risk(platform: str, seed: str, link_allowed: str) -> str:
    if platform == "Facebook Groups" and link_allowed == "unknown":
        return "medium"
    if platform in {"Reddit", "Quora"}:
        return "medium"
    if "affiliate" in seed.lower() or "mmo" in seed.lower():
        return "high"
    return "low"


def community_score(topic: str, activity: int, engagement: int, ai_interest: int, link_allowed: str, audience: str, spam: str) -> int:
    topic_match = 30 if topic == "ai_coding_tools" else 24 if topic in {"general_ai", "automation", "startup_saas"} else 18
    link_score = 10 if link_allowed == "yes" else 5 if link_allowed == "unknown" else 0
    audience_score = 10 if audience in {"developers", "founders", "marketers"} else 7
    spam_score = {"low": 10, "medium": 5, "high": 0}.get(spam, 5)
    return min(100, topic_match + activity + engagement + link_score + audience_score + spam_score + min(ai_interest, 30) - 30)


def priority_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def priority_sort(priority: str) -> int:
    return {"A": 0, "B": 1, "C": 2, "D": 3}.get(priority, 4)


def recommended_action(priority: str, link_allowed: str, spam: str) -> str:
    if priority == "A":
        return "join" if spam == "low" else "comment_only"
    if priority == "B":
        return "comment_only" if link_allowed == "unknown" else "post"
    if priority == "C":
        return "comment_only"
    return "avoid"


def posting_rules_summary(platform: str, link_allowed: str) -> str:
    if platform == "Facebook Groups":
        return "Read group rules first. Prefer value-first posts. If link policy is unclear, post without link and offer to share checklist in comments."
    if platform == "LinkedIn Groups/Pages":
        return "Professional tone. One link maximum. Avoid duplicate promotional posts."
    if platform == "X/Twitter":
        return "Keep posts short. One link maximum, usually final tweet. Max two hashtags."
    if platform == "Telegram":
        return "Short, direct, useful. Link allowed only for owned or approved channels/groups."
    if platform == "Reddit":
        return "Comment-first. Avoid self-promotion unless subreddit rules explicitly allow it."
    return "Answer-first. Avoid direct promotion unless rules allow links."


def suggested_angle(topic: str, audience: str, language: str) -> str:
    if language == "vi":
        if topic == "ai_coding_tools":
            return "Chia sẻ workflow thật: ý tưởng -> ChatGPT prompt -> Windsurf build -> Codex sửa lỗi."
        return "Chia sẻ bài học thực tế, tránh đăng link ngay khi chưa rõ luật nhóm."
    if topic == "ai_coding_tools":
        return "Real workflow: idea -> ChatGPT prompt -> Windsurf first build -> Codex repair."
    if audience == "marketers":
        return "Practical AI workflow for publishing useful content without overclaiming results."
    return "Builder note with one practical lesson and a soft checklist CTA."


def generate_group_post_drafts(communities: list[dict[str, str]]) -> list[dict[str, str]]:
    eligible = [
        row for row in communities
        if row["join_priority"] in {"A", "B"} and row["recommended_action"] in {"join", "post", "comment_only"}
    ]
    selected = select_balanced_communities(eligible, max_total=8)
    rows: list[dict[str, str]] = []
    schedule_start = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    variants = ["value_first", "soft_cta", "comment_answer", "question_post"]
    for community_index, community in enumerate(selected):
        for page_index, source_url in enumerate(FIRST_CAMPAIGN_PAGES):
            for variant in variants:
                rows.append(build_post_row(community, source_url, variant, schedule_start, len(rows)))
            if community["link_allowed"] == "yes":
                rows.append(build_post_row(community, source_url, "direct_link", schedule_start, len(rows)))
        platform_variant = platform_specific_variant(community["platform"])
        rows.append(build_post_row(community, FIRST_CAMPAIGN_PAGES[0], platform_variant, schedule_start, len(rows)))
    return rows


def select_balanced_communities(communities: list[dict[str, str]], max_total: int = 8) -> list[dict[str, str]]:
    """Pick a small cross-platform campaign set instead of overloading one platform."""
    platforms = ["Facebook Groups", "LinkedIn Groups/Pages", "X/Twitter", "Telegram", "Reddit", "Quora"]
    selected: list[dict[str, str]] = []
    for platform in platforms:
        matches = [row for row in communities if row["platform"] == platform]
        if matches:
            selected.append(matches[0])
    if len(selected) < max_total:
        selected_ids = {row["community_id"] for row in selected}
        for row in communities:
            if row["community_id"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["community_id"])
            if len(selected) >= max_total:
                break
    return selected[:max_total]


def build_post_row(community: dict[str, str], source_url: str, variant: str, schedule_start: datetime, index: int) -> dict[str, str]:
    platform = community["platform"]
    language = community["language"]
    tracked = tracked_url(source_url, platform, community["community_id"], variant)
    content = render_community_post(community, source_url, tracked, variant)
    if platform == "X/Twitter":
        content = make_x_post_safe(content, tracked)
    risk = estimate_post_risk(community, variant, content)
    post_id = stable_id(community["community_id"], source_url, variant)
    return {
        "post_id": post_id,
        "platform": platform,
        "community_id": community["community_id"],
        "community_name": community["community_name"],
        "language": language,
        "source_url": source_url,
        "tracked_url": tracked,
        "content_variant": variant,
        "content_style": content_style_for_variant(variant),
        "content": content,
        "cta": cta_for(language, variant),
        "hashtags": hashtags_for(platform, source_url),
        "estimated_risk": risk,
        "status": "pending_review",
        "schedule_time": (schedule_start + timedelta(hours=(index // 2) * 12)).isoformat(timespec="minutes"),
        "notes": "Requires human approval before publishing. External groups should be posted manually unless explicitly approved.",
    }


def make_x_post_safe(content: str, tracked: str) -> str:
    if len(content) <= 260:
        return content
    base = "Second failed fixes expose AI coding tools. My workflow: ChatGPT plans, Windsurf scaffolds, Codex repairs."
    suffix = f"{tracked} #AICoding"
    max_base = max(40, 259 - len(suffix) - 1)
    return f"{base[:max_base].rstrip()} {suffix}"


def render_community_post(community: dict[str, str], source_url: str, tracked: str, variant: str) -> str:
    vi = community["language"] == "vi"
    platform = community["platform"]
    link_allowed = community["link_allowed"] == "yes" or variant == "direct_link"
    if variant == "value_first":
        return (
            "Mình đang dùng một workflow khá thực tế: bắt đầu từ ý tưởng, nhờ ChatGPT làm rõ prompt, dùng Windsurf dựng bản đầu, rồi dùng Codex sửa lỗi khó. Bài học lớn nhất: đừng hỏi tool nào tốt nhất, hãy chia vai đúng cho từng tool."
            if vi else
            "I have been using a practical AI coding workflow: start with the idea, use ChatGPT to clarify the prompt, let Windsurf build the first version, then use Codex for focused fixes. The real lesson: do not ask which tool is best; give each tool the right job."
        )
    if variant == "soft_cta":
        base = (
            "Nếu bạn đang thử build website/app bằng AI, mình có ghi lại workflow ChatGPT -> Windsurf -> Codex theo cách dễ áp dụng cho người không chuyên code."
            if vi else
            "If you are trying to build a site or app with AI, I documented my ChatGPT -> Windsurf -> Codex workflow in a practical, non-hype way."
        )
        no_link_cta = (
            "Nếu cần mình gửi link checklist."
            if vi else
            "If helpful, I can share the checklist link in the comments."
        )
        return f"{base}\n\n{tracked}" if link_allowed else f"{base}\n\n{no_link_cta}"
    if variant == "direct_link":
        base = (
            "Mình viết lại workflow thật khi dùng ChatGPT để tạo prompt cho Windsurf, sau đó dùng Codex để sửa lỗi và hoàn thiện project."
            if vi else
            "I wrote down the real workflow I use: ChatGPT for prompt planning, Windsurf for the first build, Codex for repair and polish."
        )
        return f"{base}\n\n{tracked}"
    if variant == "comment_answer":
        return (
            "Theo trải nghiệm của mình, phần quan trọng không phải prompt dài hơn, mà là prompt rõ hơn: mục tiêu, file cần sửa, lỗi đang thấy, tiêu chí pass/fail."
            if vi else
            "From my experience, better prompts are not just longer prompts. They include the goal, files to touch, visible errors, and pass/fail criteria."
        )
    if variant == "question_post":
        return (
            "Nếu bạn dùng AI coding tool, bạn thường để tool nào làm bản đầu và tool nào sửa lỗi cuối? Mình đang tách: ChatGPT lập prompt, Windsurf dựng nhanh, Codex sửa sâu."
            if vi else
            "If you use AI coding tools, which one do you trust for the first build and which one for cleanup? I currently split it this way: ChatGPT plans, Windsurf scaffolds, Codex repairs."
        )
    if variant == "x_short":
        text = "AI coding tools get exposed on the second failed fix. My current split: ChatGPT plans, Windsurf scaffolds, Codex repairs."
        return f"{text} {tracked} #AICoding"
    if variant == "linkedin_professional":
        return (
            "A practical AI coding workflow that has worked better for me than relying on one tool:\n\n"
            "1. Start with a real project idea.\n"
            "2. Use ChatGPT to turn the idea into a clear implementation prompt.\n"
            "3. Use Windsurf to create the first working version.\n"
            "4. Test the result manually.\n"
            "5. Send screenshots and errors back to ChatGPT.\n"
            "6. Use Codex for focused repair, refactoring, SEO checks, and deployment cleanup.\n\n"
            f"The full write-up is here: {tracked}"
        )
    if variant == "telegram_short":
        return f"AI coding workflow thực tế:\nChatGPT viết prompt -> Windsurf dựng bản đầu -> Codex sửa lỗi và hoàn thiện.\n\n{tracked}" if vi else f"Practical AI coding workflow:\nChatGPT writes the prompt -> Windsurf builds the first version -> Codex fixes and polishes.\n\n{tracked}"
    return ""


def platform_specific_variant(platform: str) -> str:
    if platform == "X/Twitter":
        return "x_short"
    if platform == "LinkedIn Groups/Pages":
        return "linkedin_professional"
    if platform == "Telegram":
        return "telegram_short"
    return "value_first"


def tracked_url(path: str, platform: str, community_id: str, variant: str) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    clean_path = "/" + str(path).strip("/") + "/"
    campaign = clean_path.strip("/").replace("/", "_") or "homepage"
    source = platform_source(platform)
    params = {
        "utm_source": source,
        "utm_medium": "social",
        "utm_campaign": campaign,
        "utm_content": f"{community_id}_{variant}",
    }
    return f"{base}{clean_path}?{urlencode(params)}"


def platform_source(platform: str) -> str:
    key = platform.lower()
    if "facebook" in key:
        return "facebook_group"
    if "linkedin" in key:
        return "linkedin_group"
    if "telegram" in key:
        return "telegram_group"
    if "twitter" in key or key == "x":
        return "twitter"
    if "reddit" in key:
        return "reddit"
    if "quora" in key:
        return "quora"
    return "community"


def content_style_for_variant(variant: str) -> str:
    return {
        "value_first": "value_first",
        "soft_cta": "soft_cta",
        "direct_link": "direct_link",
        "comment_answer": "comment_style_answer",
        "question_post": "discussion_question",
        "x_short": "x_short",
        "linkedin_professional": "linkedin_professional",
        "telegram_short": "telegram_short",
    }.get(variant, variant)


def cta_for(language: str, variant: str) -> str:
    if variant in {"value_first", "comment_answer", "question_post"}:
        return "No direct link. Build trust first." if language == "en" else "Không gắn link trực tiếp. Ưu tiên chia sẻ giá trị trước."
    return "Read the workflow" if language == "en" else "Đọc quy trình thực tế"


def hashtags_for(platform: str, source_url: str) -> str:
    if platform == "X/Twitter":
        return "#AICoding #BuildInPublic"
    if platform == "LinkedIn Groups/Pages":
        return "#AICoding #AIWorkflow #BuildInPublic"
    if platform == "Telegram":
        return "#AI #Coding"
    return ""


def estimate_post_risk(community: dict[str, str], variant: str, content: str) -> str:
    if variant == "direct_link" and community["link_allowed"] != "yes":
        return "high"
    if community["spam_risk"] == "high":
        return "high"
    if community["link_allowed"] == "unknown" and "http" in content:
        return "medium"
    if community["platform"] == "X/Twitter" and len(content) > 260:
        return "high"
    return community["spam_risk"]


def count_invalid_x_posts(posts: list[dict[str, str]]) -> int:
    return sum(1 for row in posts if row["platform"] == "X/Twitter" and len(row["content"]) > 260)


def generate_join_checklist(communities: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in communities:
        if row["join_priority"] not in {"A", "B"}:
            continue
        rows.append({
            "community_id": row["community_id"],
            "platform": row["platform"],
            "community_name": row["community_name"],
            "community_url": row["community_url"],
            "join_priority": row["join_priority"],
            "recommended_action": row["recommended_action"],
            "check_rules": "Read pinned post and group rules before joining/posting.",
            "check_link_policy": "Confirm whether links are allowed. If unknown, start with no-link value post.",
            "introduce_without_link": "Introduce yourself with a useful workflow note before sharing links.",
            "status": "pending_user_review",
            "notes": row["notes"],
        })
    return rows


def generate_performance_report(communities: list[dict[str, str]], posts: list[dict[str, str]]) -> list[dict[str, str]]:
    posts_df = pd.DataFrame(posts)
    rows = []
    for community in communities:
        subset = posts_df[posts_df["community_id"] == community["community_id"]] if not posts_df.empty else pd.DataFrame()
        rows.append({
            "platform": community["platform"],
            "community_id": community["community_id"],
            "community_name": community["community_name"],
            "posts_created": str(len(subset)),
            "published_posts": str(int((subset["status"] == "published").sum())) if not subset.empty and "status" in subset.columns else "0",
            "clicks": "0",
            "impressions": "0",
            "ctr": "0.0",
            "recommendation": performance_recommendation(community, len(subset)),
        })
    return rows


def performance_recommendation(community: dict[str, str], post_count: int) -> str:
    if post_count == 0 and community["join_priority"] in {"A", "B"}:
        return "prepare_first_post"
    if community["join_priority"] == "A":
        return "high_priority_test"
    if community["recommended_action"] == "avoid":
        return "avoid"
    return "monitor"


def generate_discovery_report(communities: list[dict[str, str]], posts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"metric": "communities_discovered", "value": str(len(communities))},
        {"metric": "recommended_communities", "value": str(sum(1 for row in communities if row["status"] == "recommended"))},
        {"metric": "join_checklist_items", "value": str(sum(1 for row in communities if row["join_priority"] in {"A", "B"}))},
        {"metric": "social_drafts_created", "value": str(len(posts))},
        {"metric": "posts_pending_review", "value": str(sum(1 for row in posts if row["status"] == "pending_review"))},
        {"metric": "invalid_x_posts", "value": str(count_invalid_x_posts(posts))},
        {"metric": "auto_join_enabled", "value": "false"},
        {"metric": "external_auto_post_enabled", "value": "false"},
    ]


def merge_with_existing_status(new_rows: list[dict[str, str]], path: Path, id_col: str) -> list[dict[str, str]]:
    if not path.exists():
        return new_rows
    try:
        existing = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return new_rows
    existing_by_id = {str(row.get(id_col, "")): row for row in existing.to_dict("records")}
    merged = []
    for row in new_rows:
        old = existing_by_id.get(str(row.get(id_col, "")))
        if old:
            for field in ["status", "notes", "schedule_time"]:
                if field in row and str(old.get(field, "")).strip():
                    row[field] = str(old.get(field, ""))
        merged.append(row)
    return merged


def update_community_status(community_id: str, status: str, notes: str = "", actor: str = "dashboard") -> pd.DataFrame:
    df = load_communities()
    if df.empty or "community_id" not in df.columns:
        return df
    mask = df["community_id"].astype(str) == str(community_id)
    if mask.any():
        df.loc[mask, "status"] = status
        if notes:
            df.loc[mask, "notes"] = notes
        df.to_csv(community_recommendations_path(), index=False, encoding="utf-8-sig")
        append_action_log(actor, "update_status", "community", community_id, status, notes)
    return df


def update_post_status(post_id: str, status: str, schedule_time: str = "", notes: str = "", actor: str = "dashboard") -> pd.DataFrame:
    df = load_posts()
    if df.empty or "post_id" not in df.columns:
        return df
    mask = df["post_id"].astype(str) == str(post_id)
    if mask.any():
        df.loc[mask, "status"] = status
        if schedule_time:
            df.loc[mask, "schedule_time"] = schedule_time
        if notes:
            df.loc[mask, "notes"] = notes
        df.to_csv(community_posts_path(), index=False, encoding="utf-8-sig")
        append_action_log(actor, "update_status", "community_post", post_id, status, notes)
    return df


def load_communities() -> pd.DataFrame:
    return read_csv(community_recommendations_path(), COMMUNITY_COLUMNS)


def load_posts() -> pd.DataFrame:
    return read_csv(community_posts_path(), POST_COLUMNS)


def load_join_checklist() -> pd.DataFrame:
    return read_csv(join_checklist_path(), JOIN_CHECKLIST_COLUMNS)


def load_performance_report() -> pd.DataFrame:
    return read_csv(performance_report_path(), PERFORMANCE_COLUMNS)


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def ensure_action_log() -> None:
    if not action_log_path().exists():
        write_csv(action_log_path(), [], ACTION_LOG_COLUMNS)


def append_action_log(actor: str, action: str, object_type: str, object_id: str, status: str, notes: str = "") -> None:
    ensure_action_log()
    with action_log_path().open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACTION_LOG_COLUMNS)
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "actor": actor,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "status": status,
            "notes": notes,
        })


def stable_id(*parts: str) -> str:
    raw = "|".join(str(part).strip().lower() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    readable = "".join(ch if ch.isalnum() else "-" for ch in str(parts[-1]).lower()).strip("-")[:24]
    return f"{readable}-{digest}"


def run_community_discovery() -> dict[str, int]:
    return ensure_community_discovery_assets()
