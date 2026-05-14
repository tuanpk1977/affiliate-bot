from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import settings


SKILLS = {
    "/affiliate-check": "Analyze an affiliate program and decide promote or skip.",
    "/research": "Create a product review research plan.",
    "/funnel-planner": "Plan a path from zero to first commission.",
    "/blog": "Generate an SEO blog article draft.",
    "/landing": "Generate affiliate landing page copy.",
    "/social": "Create multi-channel social drafts.",
    "/video-script": "Create seven short video scripts.",
    "/repurpose": "Repurpose one review or idea into multiple formats.",
    "/aeo-check": "Track AI search visibility manually.",
    "/compliance-check": "Check content before publishing.",
    "/outreach": "Generate backlink and outreach messages.",
    "/analytics-note": "Turn manual traffic and conversion notes into next actions.",
}


def list_skills() -> list[dict[str, str]]:
    return [{"command": command, "purpose": purpose} for command, purpose in SKILLS.items()]


def run_skill(command: str, inputs: dict[str, str]) -> dict[str, str]:
    command = command if command in SKILLS else "/research"
    product = clean(inputs.get("product_name") or inputs.get("product") or "the product")
    keyword = clean(inputs.get("main_keyword") or inputs.get("keyword") or f"{product} review")
    audience = clean(inputs.get("target_audience") or inputs.get("audience") or "small business buyers")
    competitors = clean(inputs.get("competitors") or "category alternatives")
    content = clean(inputs.get("content") or inputs.get("notes") or "")

    handlers = {
        "/affiliate-check": affiliate_check,
        "/research": research_plan,
        "/funnel-planner": funnel_planner,
        "/blog": blog_draft,
        "/landing": landing_copy,
        "/social": social_posts,
        "/video-script": video_scripts,
        "/repurpose": repurpose,
        "/aeo-check": aeo_check,
        "/compliance-check": compliance_check,
        "/outreach": outreach_messages,
        "/analytics-note": analytics_note,
    }
    output = handlers[command](product, keyword, audience, competitors, content, inputs)
    return {"command": command, "status": "Draft", "output": output}


def save_draft(command: str, inputs: dict[str, str], output: str, status: str = "Draft") -> Path:
    path = settings.data_dir / "affiliate_os_drafts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    drafts = []
    if path.exists():
        try:
            drafts = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            drafts = []
    drafts.append(
        {
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "command": command,
            "status": status,
            "inputs": inputs,
            "output": output,
        }
    )
    path.write_text(json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def affiliate_check(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    commission = float_or_zero(inputs.get("affiliate_commission") or inputs.get("commission"))
    cookie = float_or_zero(inputs.get("cookie_duration") or inputs.get("cookie_days"))
    price = float_or_zero(inputs.get("product_price") or inputs.get("price"))
    competition = clean(inputs.get("competition_level") or "Medium")
    score = 50
    score += 18 if commission >= 25 else 10 if commission >= 10 else 3
    score += 8 if cookie >= 30 else 3
    score += 8 if price >= 50 else 3
    score -= 12 if competition.lower() == "high" else 0
    score = max(35, min(92, round(score)))
    decision = "PROMOTE with small test" if score >= 75 else "WATCH and verify" if score >= 60 else "SKIP for now"
    return f"""Affiliate Check: {product}

Score: {score}/100
Risk: {"Medium" if score >= 60 else "High"}
Recommendation: {decision}

Pros:
- Clear audience fit: {audience}
- Commission signal: {commission:g}
- Cookie duration: {cookie:g} days

Cons / risks:
- Competition level: {competition}
- Payout terms must be verified manually.
- Traffic policy, trademark bidding, and direct linking rules must be checked before ads.

Next action:
- Create a review landing page.
- Avoid brand bidding unless allowed.
- Test only after affiliate approval and policy verification."""


def research_plan(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Research Plan: {product}

Review angle:
- Help {audience} decide whether {product} is a practical fit.

Search intent:
- Main intent: comparison and buyer research.
- Primary keyword: {keyword}
- Secondary keywords: {product} alternatives, {product} pricing, {product} pros and cons, {product} vs {competitors}

Content outline:
1. Short answer
2. What {product} does
3. Key features
4. Pros and cons
5. Pricing note
6. Best for / not best for
7. Alternatives
8. FAQ
9. Final verdict

Comparison opportunities:
- {product} vs {competitors}
- Best alternatives to {product}

FAQ ideas:
- Is {product} worth it?
- Who should use {product}?
- What are the best alternatives?
- Does pricing change?
- Are affiliate links used?"""


def funnel_planner(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Funnel Planner: {product}

Week 1 content plan:
- Publish {product} review.
- Publish {product} alternatives article.
- Create one LinkedIn post and one Vietnamese Facebook story.

Week 2 content plan:
- Publish {product} vs {competitors}.
- Add FAQ and internal links.
- Share one short video script per day.

Traffic sources:
- SEO, LinkedIn, Facebook groups where allowed, Medium, Dev.to if technical.

Landing page idea:
- Research-style review page with disclosure, pros/cons, alternatives, and CTA.

Newsletter idea:
- "New AI/SaaS tool research notes every week."

CTA strategy:
- Soft CTA: Visit official website.
- Use affiliate link only after approval.

Conversion tracking checklist:
- Page URL, clicks, conversions, commission, notes, next action."""


def blog_draft(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Title: {keyword.title()}: A Practical Guide for {audience.title()}

Meta title: {keyword.title()} - Practical Buyer Guide
Meta description: Learn how to evaluate {product}, compare alternatives, check pricing notes, and avoid common SaaS buying mistakes.

Intro:
Choosing {product} should start with workflow fit, not hype. This guide explains what to check, who it may help, and what to verify before buying.

Sections:
1. What problem does {product} solve?
2. Who should consider it?
3. Key features to evaluate
4. Pricing and policy notes
5. Alternatives to compare
6. Final checklist

FAQ:
- Is {product} worth it?
- What should I verify first?
- Are there alternatives?
- Can I use it for business?
- Are affiliate links used?

CTA:
- Read the full {product} review.

Internal links:
- /{slug(product)}/
- /comparisons/
- /affiliate-disclosure/

Affiliate disclosure:
Some links may be affiliate links. We may earn a commission at no extra cost to you."""


def landing_copy(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Landing Page Copy: {product}

Hero headline:
Is {product} the right tool for your workflow?

Subheadline:
A practical review for {audience} comparing features, limitations, alternatives, and pricing notes.

Pain points:
- Too many tools look similar.
- Pricing and limits are hard to compare.
- Real workflow fit is unclear.

Benefits:
- Clear pros and cons.
- Safer buyer checklist.
- Alternatives included.

Social proof placeholder:
- Add real user quotes only after permission. Do not invent testimonials.

CTA sections:
- Primary: Visit Official Website
- Secondary: Read Full Review

FAQ:
- Who is {product} best for?
- What are the alternatives?
- Should I verify pricing?

Disclosure:
Some links may be affiliate links. We may earn a commission at no extra cost to you."""


def social_posts(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Facebook Vietnamese storytelling:
Mình thấy nhiều người chọn tool AI chỉ vì nghe tên nổi. Nhưng với {product}, điều cần hỏi là: nó có giúp đúng workflow của mình không? Trước khi mua, nên kiểm tra pricing, giới hạn tính năng, alternatives và policy. Mình đã viết một bài review kiểu nghiên cứu để bạn đọc nhanh trước khi quyết định. CTA mềm: đọc review trước khi đăng ký.

X English short hook:
Before buying {product}, check workflow fit, pricing limits, alternatives, and policy. Hype is not a buying strategy.

LinkedIn English professional:
When evaluating {product}, I would not start with features. I would start with use case fit, switching cost, pricing risk, and whether the tool improves a repeatable workflow. A research-first review reduces poor SaaS decisions.

Telegram Vietnamese direct:
Checklist nhanh cho {product}: giá hiện tại, giới hạn plan, alternatives, chính sách affiliate/ads, có phù hợp workflow không. Đừng mua chỉ vì trend.

Dev.to English technical:
If {product} fits a developer or automation workflow, document the exact task it improves, the input/output process, and how it compares with {competitors}. Tool adoption should be measured by repeatable workflow improvement.

Medium article draft:
Title: How to Evaluate {product} Without Falling for SaaS Hype
Include: problem, evaluation checklist, alternatives, pricing notes, disclosure, final recommendation."""


def video_scripts(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    themes = ["The Problem", "The Discovery", "The Feature", "The Result", "The Comparison", "The Objection", "The CTA"]
    lines = []
    for idx, theme in enumerate(themes, start=1):
        mention = "Yes" if idx in {2, 3, 5, 7} else "Optional"
        lines.append(f"""Video {idx}: {theme}
Hook: Before you choose another SaaS tool, check this.
Scene idea: Screen recording or simple talking head with checklist overlay.
Voiceover: Today I am evaluating {product} for {audience}. The goal is not hype; it is workflow fit.
Text on screen: Verify pricing, features, alternatives, and policy.
CTA: Read the full review before signing up.
Mention brand/tool: {mention}""")
    return "\n\n".join(lines)


def repurpose(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    source = content or f"{product} helps {audience} compare workflow fit, pricing, and alternatives."
    return f"""Repurposed Drafts from: {product}

Facebook post:
{source} Điều quan trọng là kiểm tra kỹ trước khi mua hoặc chạy ads.

LinkedIn post:
A good {product} review should explain use case fit, limitations, alternatives, and pricing verification.

X thread:
1/ Buying SaaS? Start with workflow fit.
2/ For {product}, verify pricing, terms, and alternatives.
3/ Do not rely on hype.

Medium article:
Turn the review into a practical buyer guide with sections for problem, features, pricing, alternatives, and FAQ.

Telegram:
Checklist {product}: pricing, policy, alternatives, CTA, disclosure.

TikTok script:
Hook: "Do not buy {product} before checking these 5 things."

Email newsletter:
Subject: New research note: {product}
Body: Summary, key tradeoffs, alternatives, and link to review."""


def aeo_check(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    mentioned = clean(inputs.get("was_my_site_mentioned") or "No")
    platform = clean(inputs.get("ai_platform") or "ChatGPT/Gemini/Perplexity")
    score = 75 if mentioned.lower() in {"yes", "true"} else 45
    return f"""AEO Check: {keyword}

AI platform: {platform}
Visibility score: {score}/100
Was my site mentioned? {mentioned}
Competitors mentioned: {competitors}

Gap analysis:
- Add direct short-answer sections.
- Add comparison pages and FAQ schema.
- Build citations through non-spammy outreach.

Content recommendation:
- Create a concise answer page for: {keyword}

Off-page recommendation:
- Share useful summaries on LinkedIn, Medium, and relevant communities without auto-spam."""


def compliance_check(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    lower = content.lower()
    issues = []
    if "affiliate" not in lower and "commission" not in lower:
        issues.append("Missing affiliate disclosure.")
    for phrase in ["guaranteed", "100% success", "best forever", "easy money", "guaranteed income"]:
        if phrase in lower:
            issues.append(f"Risky wording found: {phrase}")
    if "tested" in lower and "placeholder" in lower:
        issues.append("Testing claim is marked as placeholder; verify before publishing.")
    if not issues:
        issues.append("No major compliance issue detected, but manual review is still required.")
    return "Compliance Check\n\n" + "\n".join(f"- {issue}" for issue in issues) + "\n\nStatus: Draft only. Review before publishing. Do not spam."


def outreach_messages(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    return f"""Email version:
Subject: Useful resource for your {keyword} page
Hi, I published a practical research guide on {product} for {audience}. If it is useful for your readers, you may consider adding it as an additional resource. No pressure either way.

LinkedIn version:
Hi, I saw your content around {keyword}. I recently wrote a research-style review of {product} with pros, cons, pricing notes, and alternatives. Happy to share if useful.

Facebook message version:
Mình có viết một bài review nghiên cứu về {product}, tập trung vào checklist trước khi mua. Nếu phù hợp với group/page của bạn thì mình gửi link tham khảo.

Link insertion request:
Would you consider referencing the guide as a helpful external resource if it adds value to your article?

Guest post pitch:
Proposed topic: How to evaluate {product} and alternatives safely before buying."""


def analytics_note(product: str, keyword: str, audience: str, competitors: str, content: str, inputs: dict[str, str]) -> str:
    traffic = float_or_zero(inputs.get("traffic"))
    clicks = float_or_zero(inputs.get("clicks"))
    conversions = float_or_zero(inputs.get("conversions"))
    commission = float_or_zero(inputs.get("commission"))
    ctr = round((clicks / traffic) * 100, 2) if traffic else 0
    cr = round((conversions / clicks) * 100, 2) if clicks else 0
    return f"""Analytics Note

Page URL: {clean(inputs.get("page_url") or "")}
Traffic: {traffic:g}
Clicks: {clicks:g}
Conversions: {conversions:g}
Commission: {commission:g}
CTR: {ctr}%
Conversion rate: {cr}%

What is working:
- {"Traffic exists; improve CTA testing." if traffic else "No traffic signal yet."}

What to improve:
- Add internal links, improve short answer, test CTA wording, and check search intent.

Next action:
- Keep status as Draft/Approved manually. Do not auto-post or auto-spend."""


def clean(value: object) -> str:
    return str(value or "").strip()


def float_or_zero(value: object) -> float:
    try:
        return float(str(value).replace("%", "").strip() or 0)
    except ValueError:
        return 0.0


def slug(text: str) -> str:
    return "-".join(clean(text).lower().replace(".", "").split()) or "review"
