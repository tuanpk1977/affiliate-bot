from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from modules.programmatic_page_utils import (
    affiliate_disclosure,
    breadcrumb_schema,
    faq_html,
    faq_schema,
    item_list_schema,
    offer_map,
    review_url,
    shell,
    slugify,
    write_page,
)


COMPARISONS = [
    {
        "slug": "chatgpt-vs-claude",
        "left": "ChatGPT",
        "right": "Claude",
        "category": "AI assistants",
        "left_fit": "broad everyday assistance, multimodal workflows, plugin-like product connections, fast ideation, coding help, and repeatable business drafting",
        "right_fit": "long document review, careful rewriting, structured reasoning, policy-sensitive drafting, and calm editorial analysis",
        "verdict": "Choose ChatGPT if you want the broadest daily assistant for mixed tasks; choose Claude if your workflow depends on long-context reading, careful writing, and document-heavy analysis.",
        "alternatives": ["Gemini", "Perplexity", "Notion AI"],
    },
    {
        "slug": "chatgpt-vs-gemini",
        "left": "ChatGPT",
        "right": "Gemini",
        "category": "AI assistants",
        "left_fit": "general-purpose analysis, writing, brainstorming, coding help, custom workflows, and flexible personal productivity",
        "right_fit": "Google Workspace users, search-adjacent research, Gmail and Docs workflows, and teams already standardized on Google services",
        "verdict": "Choose ChatGPT for flexible cross-functional AI work; choose Gemini when your team already lives in Google Workspace and wants AI close to those apps.",
        "alternatives": ["Claude", "Perplexity", "Notion AI"],
    },
    {
        "slug": "claude-vs-gemini",
        "left": "Claude",
        "right": "Gemini",
        "category": "AI assistants",
        "left_fit": "long-form editing, summarizing large documents, comparing policy text, writing with a measured tone, and careful reasoning",
        "right_fit": "Google-native productivity, research inside a Google ecosystem, fast workspace support, and users who prefer Google account integration",
        "verdict": "Choose Claude for document-heavy thinking and editorial quality; choose Gemini when Google ecosystem fit matters more than standalone writing depth.",
        "alternatives": ["ChatGPT", "Perplexity", "Notion AI"],
    },
    {
        "slug": "cursor-vs-windsurf",
        "left": "Cursor",
        "right": "Windsurf",
        "category": "AI coding tools",
        "left_fit": "developers who want an AI-first editor with strong codebase chat, inline edits, refactors, and fast adoption from a VS Code-like workflow",
        "right_fit": "builders testing agent-style coding, larger multi-file edits, rapid prototyping, and a newer AI coding environment",
        "verdict": "Choose Cursor for a mature AI coding editor workflow; test Windsurf when you want to compare agent-style coding and fast prototype loops.",
        "alternatives": ["GitHub Copilot", "Replit", "Codex"],
    },
    {
        "slug": "lovable-vs-bolt",
        "left": "Lovable",
        "right": "Bolt",
        "category": "AI app builders",
        "left_fit": "non-technical founders, product managers, and builders who want to turn app ideas into full-stack prototypes through prompts",
        "right_fit": "browser-based app generation, quick front-end experiments, deployable prototypes, and builders who want to iterate quickly in a web IDE",
        "verdict": "Choose Lovable when the priority is product-shaped app generation from a clear idea; choose Bolt when you want a fast browser IDE for iterative web app builds.",
        "alternatives": ["Replit", "Cursor", "Windsurf"],
    },
    {
        "slug": "claude-vs-perplexity",
        "left": "Claude",
        "right": "Perplexity",
        "category": "AI research tools",
        "left_fit": "deep reading, synthesis, long-document rewriting, editorial analysis, and private drafting from materials you provide",
        "right_fit": "answer discovery with citations, web research, source finding, topic scanning, and fast comparison of public information",
        "verdict": "Choose Claude when you already have documents to analyze; choose Perplexity when the job starts with finding sources and understanding the current public web.",
        "alternatives": ["ChatGPT", "Gemini", "Notion AI"],
    },
    {
        "slug": "chatgpt-vs-perplexity",
        "left": "ChatGPT",
        "right": "Perplexity",
        "category": "AI assistants and research tools",
        "left_fit": "drafting, planning, coding help, structured analysis, creative workflows, and multi-step assistant work beyond web research",
        "right_fit": "citation-led search, source discovery, quick research briefs, competitive scans, and fact-finding workflows",
        "verdict": "Choose ChatGPT for a flexible work assistant; choose Perplexity when citation-backed research and source discovery are the core job.",
        "alternatives": ["Claude", "Gemini", "Notion AI"],
    },
    {
        "slug": "replit-vs-cursor",
        "left": "Replit",
        "right": "Cursor",
        "category": "AI coding tools",
        "left_fit": "browser-based coding, hosted projects, beginner-friendly app experiments, quick deployment, and team prototypes without local setup",
        "right_fit": "local professional development, existing repositories, codebase-aware edits, refactors, and AI-assisted engineering inside an editor",
        "verdict": "Choose Replit for hosted browser development and quick deployment; choose Cursor for serious local codebase work in an AI-first editor.",
        "alternatives": ["Windsurf", "GitHub Copilot", "Bolt"],
    },
    {
        "slug": "surfer-seo-vs-frase",
        "left": "Surfer SEO",
        "right": "Frase",
        "category": "AI SEO content tools",
        "left_fit": "content optimization, SERP-based term guidance, on-page scoring, briefs, and teams improving articles for organic search",
        "right_fit": "content briefs, research-driven outlines, question discovery, topic coverage, and writers who need planning help before drafting",
        "verdict": "Choose Surfer SEO if optimization and scoring are the main job; choose Frase if research briefs and structured content planning matter more.",
        "alternatives": ["Semrush", "Ahrefs AI", "Jasper"],
    },
    {
        "slug": "jasper-vs-copy-ai",
        "left": "Jasper",
        "right": "Copy.ai",
        "category": "AI writing tools",
        "left_fit": "brand voice, marketing campaign content, team governance, reusable content workflows, and structured marketing production",
        "right_fit": "go-to-market copy, sales sequences, quick drafts, workflow automation, and teams moving from blank page to campaign ideas fast",
        "verdict": "Choose Jasper for brand-led marketing content operations; choose Copy.ai for fast GTM drafting and sales-oriented copy workflows.",
        "alternatives": ["ChatGPT", "Claude", "Notion AI"],
    },
    {
        "slug": "cursor-vs-github-copilot",
        "left": "Cursor",
        "right": "GitHub Copilot",
        "category": "AI coding tools",
        "left_fit": "AI-first editor workflows, codebase chat, multi-file edits, refactors, and developers who want the assistant built into the editor experience",
        "right_fit": "completion-first coding help, GitHub-native teams, familiar IDE setups, and developers who want AI assistance without changing editors",
        "verdict": "Choose Cursor when you want an AI-first editor; choose GitHub Copilot when you want broad IDE support and GitHub-native coding assistance.",
        "alternatives": ["Windsurf", "Replit", "Codex"],
    },
    {
        "slug": "make-vs-zapier",
        "left": "Make",
        "right": "Zapier",
        "category": "automation platforms",
        "left_fit": "visual multi-step workflows, branching logic, detailed scenario design, and teams that want more control over automation structure",
        "right_fit": "fast app connections, simple automation setup, broad app coverage, and teams that want beginner-friendly workflow deployment",
        "verdict": "Choose Make for complex visual automation; choose Zapier for fast setup and broad app connectivity.",
        "alternatives": ["ActiveCampaign", "HubSpot", "Notion AI"],
    },
    {
        "slug": "semrush-vs-ahrefs",
        "left": "Semrush",
        "right": "Ahrefs",
        "category": "SEO platforms",
        "left_fit": "broad SEO and marketing research, keyword tracking, competitive analysis, content planning, and multi-channel marketing teams",
        "right_fit": "backlink analysis, organic search research, competitor link discovery, and teams that prioritize SEO data depth",
        "verdict": "Choose Semrush for a broader marketing suite; choose Ahrefs when backlink and organic search research depth matter most.",
        "alternatives": ["Surfer SEO", "Frase", "Ahrefs AI"],
    },
    {
        "slug": "canva-vs-gamma",
        "left": "Canva",
        "right": "Gamma",
        "category": "AI design and presentation tools",
        "left_fit": "templates, social graphics, brand kits, simple design production, and teams creating many visual assets",
        "right_fit": "presentation-style documents, quick narrative pages, outline-to-deck workflows, and teams that need polished storytelling fast",
        "verdict": "Choose Canva for broad visual design production; choose Gamma for fast presentation and document-style storytelling.",
        "alternatives": ["AdCreative AI", "Jasper", "ChatGPT"],
    },
    {
        "slug": "elevenlabs-vs-murf",
        "left": "ElevenLabs",
        "right": "Murf",
        "category": "AI voice tools",
        "left_fit": "natural-sounding AI voices, creator audio, multilingual narration, and developers or creators testing voice quality",
        "right_fit": "business voiceovers, training content, presentations, and teams that need a structured voiceover workflow",
        "verdict": "Choose ElevenLabs for high-quality voice generation experiments; choose Murf for business-friendly voiceover production workflows.",
        "alternatives": ["Synthesia", "Runway", "Descript"],
    },
    {
        "slug": "runway-vs-pika",
        "left": "Runway",
        "right": "Pika",
        "category": "AI video tools",
        "left_fit": "generative video experiments, visual editing, creative iteration, and teams testing AI video production workflows",
        "right_fit": "short AI video generation, quick creative tests, lightweight prompt-to-video workflows, and rapid visual ideation",
        "verdict": "Choose Runway for deeper creative video workflows; choose Pika for fast short-form AI video experimentation.",
        "alternatives": ["Synthesia", "Midjourney", "ElevenLabs"],
    },
    {
        "slug": "notion-ai-vs-clickup-ai",
        "left": "Notion AI",
        "right": "ClickUp AI",
        "category": "AI productivity tools",
        "left_fit": "workspace notes, docs, wikis, summaries, and teams already managing knowledge in Notion",
        "right_fit": "project management, task execution, status updates, and teams already coordinating work in ClickUp",
        "verdict": "Choose Notion AI when knowledge work lives in Notion; choose ClickUp AI when project execution and tasks are the center of the workflow.",
        "alternatives": ["ChatGPT", "Claude", "Reclaim AI"],
    },
]


def generate_comparison_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    offers = offer_map(offer_scores)
    pages = []
    for comparison in COMPARISONS:
        slug = comparison["slug"]
        left = comparison["left"]
        right = comparison["right"]
        category = comparison["category"]
        title = f"{left} vs {right}: Which {category} should you choose?"
        description = (
            f"Long-form {left} vs {right} comparison with a decision table, pricing notes, "
            "pros and cons, alternatives, affiliate disclosure, internal links, and FAQ schema."
        )
        path = f"/comparisons/{slug}/"
        questions = [
            f"Is {left} better than {right}?",
            f"Who should choose {left}?",
            f"Who should choose {right}?",
            f"How should teams compare {left} and {right} pricing?",
            f"What are the best alternatives to {left} and {right}?",
            "Does this comparison include affiliate links?",
        ]
        body = render_comparison_body(output, comparison, offers, questions)
        page = shell(
            title,
            description,
            path,
            body,
            [
                faq_schema(questions),
                breadcrumb_schema(title, path),
                item_list_schema(title, [left, right] + comparison["alternatives"], path),
            ],
        )
        write_page(output, f"comparisons/{slug}", page)
        pages.append({"slug": f"comparisons/{slug}", "title": title, "type": "comparison"})
    return pages


def render_comparison_body(output: Path, comparison: dict[str, object], offers: dict[str, dict], questions: list[str]) -> str:
    slug = str(comparison["slug"])
    left = str(comparison["left"])
    right = str(comparison["right"])
    category = str(comparison["category"])
    left_fit = str(comparison["left_fit"])
    right_fit = str(comparison["right_fit"])
    verdict = str(comparison["verdict"])
    alternatives = [str(item) for item in comparison["alternatives"]]
    left_review = safe_review_url(output, left)
    right_review = safe_review_url(output, right)
    left_go = go_url(left, offers, left_review)
    right_go = go_url(right, offers, right_review)
    alternative_links = " ".join(
        f"<li><a href='{safe_review_url(output, tool)}'>{html.escape(tool)} review</a> - useful if neither side matches your budget, stack, or workflow.</li>"
        for tool in alternatives
    )
    related_links = related_comparison_links(slug)
    table_rows = comparison_table_rows(left, right, category, left_fit, right_fit, left_review, right_review)

    return f"""<section class='hero card'><h1>{html.escape(left)} vs {html.escape(right)}</h1><p>{html.escape(verdict)}</p><p>This long-form guide is written for buyers comparing {html.escape(category)} before they commit budget, migrate workflows, or recommend a tool to a team. It focuses on real decision criteria: daily use cases, pricing risk, quality control, collaboration, integrations, vendor fit, and what to verify on the official site before purchasing.</p><p><a class='btn' href='{html.escape(left_review)}'>Read {html.escape(left)} review</a><a class='btn secondary' href='{html.escape(right_review)}'>Read {html.escape(right)} review</a></p></section>
{affiliate_disclosure()}
<section class='card'><h2>Quick Verdict</h2><p><strong>{html.escape(verdict)}</strong></p><p>The most practical way to compare {html.escape(left)} and {html.escape(right)} is to ignore brand popularity for a moment and map each tool to the work you repeat every week. A solo creator, a marketing team, a software team, and an agency will judge the same product very differently because the cost of switching, the review process, and the expected output are different. Treat this page as a shortlist framework, then run a hands-on test with your own prompts, source material, project files, and approval process.</p></section>
<section class='card'><h2>Comparison Table</h2><table><thead><tr><th>Criteria</th><th>{html.escape(left)}</th><th>{html.escape(right)}</th></tr></thead><tbody>{table_rows}</tbody></table></section>
<section class='grid'><div class='card'><h2>Choose {html.escape(left)} If</h2><p>{html.escape(left_fit.capitalize())} are the center of your workflow. {html.escape(left)} is the stronger shortlist candidate when those jobs happen often enough that saving a few minutes per task compounds into real operating leverage.</p><ul><li>You want the workflow strength described above more than a generic feature checklist.</li><li>Your team can test the tool with real tasks before committing to an annual plan.</li><li>You value a stable review process where humans still approve important outputs.</li></ul><p><a class='btn' rel='nofollow sponsored' href='{html.escape(left_go, quote=True)}'>Visit {html.escape(left)}</a></p></div><div class='card'><h2>Choose {html.escape(right)} If</h2><p>{html.escape(right_fit.capitalize())} are more important for your team. {html.escape(right)} is the better candidate when its workflow shape removes friction that {html.escape(left)} would leave in place.</p><ul><li>You need the specific strengths above more than broad category coverage.</li><li>Your current stack makes {html.escape(right)} easier to adopt or manage.</li><li>You can verify pricing, limits, and policy details before sending paid traffic.</li></ul><p><a class='btn secondary' rel='nofollow sponsored' href='{html.escape(right_go, quote=True)}'>Visit {html.escape(right)}</a></p></div></section>
<section class='card'><h2>How To Read This Comparison</h2>{decision_framework(left, right, category)}</section>
<section class='card'><h2>{html.escape(left)} Review Notes</h2>{tool_review_notes(left, right, left_fit, category)}</section>
<section class='card'><h2>{html.escape(right)} Review Notes</h2>{tool_review_notes(right, left, right_fit, category)}</section>
<section class='grid'><div class='card'><h2>{html.escape(left)} Pros</h2>{pros_list(left, left_fit)}</div><div class='card'><h2>{html.escape(left)} Cons</h2>{cons_list(left, right)}</div><div class='card'><h2>{html.escape(right)} Pros</h2>{pros_list(right, right_fit)}</div><div class='card'><h2>{html.escape(right)} Cons</h2>{cons_list(right, left)}</div></section>
<section class='card'><h2>Pricing And Value</h2>{pricing_section(left, right)}</section>
<section class='card'><h2>Workflow Fit</h2>{workflow_section(left, right, category)}</section>
<section class='card'><h2>Quality Control And Risk</h2>{risk_section(left, right)}</section>
<section class='card'><h2>Team Adoption Checklist</h2>{adoption_section(left, right)}</section>
<section class='card'><h2>Alternatives To Consider</h2><p>If neither tool is a clean fit, compare these related options before buying:</p><ul>{alternative_links}</ul><p>For broader research, visit the <a href='/reviews/'>AI tool reviews library</a>, the <a href='/comparisons/'>comparison hub</a>, and relevant category pages such as <a href='/category/ai-coding-tools/'>AI coding tools</a>, <a href='/category/ai-writing-tools/'>AI writing tools</a>, and <a href='/category/ai-seo-tools/'>AI SEO tools</a>.</p></section>
<section class='card'><h2>Related Comparisons</h2><ul>{related_links}</ul></section>
<section class='card'><h2>Buying Recommendation</h2>{buying_recommendation(left, right, verdict)}</section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"""


def comparison_table_rows(left: str, right: str, category: str, left_fit: str, right_fit: str, left_review: str, right_review: str) -> str:
    rows = [
        ("Best fit", left_fit, right_fit),
        ("Main buyer question", f"Does {left} improve the repeated work that matters most?", f"Does {right} remove more friction than {left} for the same work?"),
        ("Setup effort", "Run a small pilot with real assets, prompts, files, or workflows before inviting a full team.", "Run the same pilot so quality, speed, and limits can be compared fairly."),
        ("Pricing check", "Confirm monthly and annual pricing, usage caps, seat costs, refund terms, and commercial usage rights.", "Confirm the same pricing details and avoid relying on old screenshots or third-party summaries."),
        ("Collaboration", "Best when the team has a clear review process and understands where AI output can be used.", "Best when the tool fits existing approvals, handoffs, and quality checks."),
        ("Internal links", f"<a href='{html.escape(left_review)}'>{html.escape(left)} review</a>", f"<a href='{html.escape(right_review)}'>{html.escape(right)} review</a>"),
        ("Category", f"{left} is one candidate in the {category} category.", f"{right} is the counterpoint to compare before buying."),
    ]
    return "".join(
        f"<tr><td>{html.escape(label)}</td><td>{left_value}</td><td>{right_value}</td></tr>"
        for label, left_value, right_value in rows
    )


def decision_framework(left: str, right: str, category: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            f"Start by defining the job-to-be-done. A {category} page can easily become a list of features, but feature lists do not tell you whether the tool will survive daily use. Write down the three tasks you do most often, the source material those tasks require, the person who approves the final output, and the places where work currently slows down. Then test {left} and {right} against those exact tasks.",
            f"Use the same inputs for both products. If you compare {left} with a clean prompt and {right} with a messy prompt, the result is not useful. For writing tools, use the same brief and brand examples. For coding tools, use the same repository issue. For research tools, use the same question and source requirements. For SEO tools, use the same target keyword and content draft.",
            f"Score outputs on usefulness, not on surprise. A tool that produces a flashy first draft may still create more work if your team has to rewrite every result. A quieter tool may be better if it follows instructions, preserves context, and makes review easier. The right winner is the one that reduces total cycle time while keeping quality acceptable.",
            f"Finally, separate personal preference from team adoption. One person may love {left} because it matches their habits, while another may prefer {right} because it fits the existing stack. Before buying for a team, ask whether onboarding, permissions, billing, documentation, and cancellation are clear enough for the way your organization buys software.",
        ]
    )


def tool_review_notes(tool: str, rival: str, fit: str, category: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            f"{tool} is worth testing when your main work involves {fit}. In a practical buying process, that means you should not judge {tool} only by demos or social media examples. Put it inside a real task where the output has to be reviewed, edited, approved, and shipped.",
            f"The strongest case for {tool} is workflow alignment. If the tool makes the first useful version faster, keeps context available, and reduces manual switching between apps, it may justify the subscription even if {rival} has a similar feature on paper. The weaker case is when your team only needs occasional help and does not have a repeatable process.",
            f"Teams should also check how {tool} handles collaboration. A {category} product can look excellent for a solo user but become messy when five people need shared projects, permission controls, consistent prompts, billing visibility, and an audit trail. If those details are unclear, keep the pilot small.",
            f"Before buying {tool}, verify the latest terms directly on the vendor site. Pricing, plan limits, model access, exports, data controls, commercial usage, and support promises can change. This comparison is a decision guide, but the final purchase decision should use current vendor documentation.",
        ]
    )


def pros_list(tool: str, fit: str) -> str:
    items = [
        f"Strong fit when the repeated job involves {fit}.",
        "Can reduce blank-page time when the team provides clear instructions and source material.",
        "Useful for pilots because results can be tested against real tasks before a larger rollout.",
        "Works best when paired with human review, documented prompts, and a clear approval workflow.",
        "May help teams standardize a repeatable workflow instead of relying on one-off experiments.",
    ]
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def cons_list(tool: str, rival: str) -> str:
    items = [
        f"{tool} may be the wrong choice if {rival} fits your existing stack, budget, or approval process better.",
        "Output quality can vary when prompts, context, source files, or user expectations are vague.",
        "Published pricing and plan limits can change, so old reviews may be inaccurate.",
        "Teams still need review rules for factual accuracy, brand voice, privacy, and compliance.",
        "A good demo does not guarantee that the tool will handle your edge cases or production workflow.",
    ]
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def pricing_section(left: str, right: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            f"Pricing is one of the easiest parts of a {left} vs {right} comparison to get wrong because SaaS vendors change plans, usage limits, model access, and trial terms. Treat every price you see in a review as a starting point, then verify the current plan page before you buy.",
            f"Compare the cost per active user, not only the headline monthly price. If {left} charges in a way that matches your usage pattern, it may be cheaper even when the visible plan looks higher. If {right} includes features that would otherwise require extra tools, it may create better value even with a higher subscription.",
            "Look for hidden operational costs. These include onboarding time, prompt setup, migration, template maintenance, review time, export limitations, and the effort required to train the team. A low subscription price can become expensive if the tool creates quality problems or forces manual workarounds.",
            "For affiliate and editorial sites, also check whether the vendor allows commercial use, public examples, screenshots, claims, and partner promotion. If the tool will support client work, confirm that the terms allow the type of work you plan to deliver.",
        ]
    )


def workflow_section(left: str, right: str, category: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            f"The best {category} choice is usually the tool that fits the workflow you already run, not the tool with the longest feature list. If your current process depends on handoffs, approvals, exports, or integrations, test those details before choosing between {left} and {right}.",
            f"For solo users, the most important questions are speed and clarity. Can {left} or {right} help you get from idea to useful output faster? Can you understand what the tool changed? Can you recover when the first result is weak? If a product feels powerful but confusing, the real adoption rate may be low.",
            "For teams, the important questions are consistency and governance. A team needs shared conventions for prompts, examples, quality review, naming, folders, billing, and permission levels. Without those conventions, even a strong AI tool can create scattered work that is hard to reuse.",
            f"Run the pilot over several days instead of judging one session. Some tools feel impressive during the first hour but reveal limitations after repeated tasks. Others feel plain at first but become more valuable as you build templates, reusable instructions, or project context. That is why a fair {left} vs {right} test needs repeated use.",
        ]
    )


def risk_section(left: str, right: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            f"Both {left} and {right} should be used with a review process. AI output can be incomplete, outdated, overconfident, or poorly matched to your brand. The safer workflow is to use the tool for drafting, research support, exploration, or first-pass structure, then let a human verify the final decision.",
            "If the work includes legal, medical, financial, hiring, or compliance-sensitive material, do not rely on a tool output without qualified review. Even when a model sounds confident, the responsibility for the final published or business decision remains with the user.",
            f"Data handling also matters. Before uploading private documents, customer information, source code, or client materials into {left} or {right}, review the vendor's privacy policy, data retention settings, enterprise controls, and whether your organization requires a specific approval process.",
            "Quality control should be explicit. Keep a checklist for factual accuracy, citations, tone, hallucination risk, copyright risk, data exposure, and final human approval. A tool that fits this checklist is usually safer than a tool that only produces a more impressive first draft.",
        ]
    )


def adoption_section(left: str, right: str) -> str:
    items = [
        f"Define three real tasks that represent your weekly use case for {left} and {right}.",
        "Use identical prompts, files, briefs, keywords, or project issues during the pilot.",
        "Measure time saved after review, not time saved before review.",
        "Check whether outputs can be exported, shared, edited, and approved without friction.",
        "Verify plan limits, cancellation terms, data policy, and commercial usage rights.",
        "Ask the actual users which product they would keep using after the pilot ends.",
        "Document the winning workflow so the tool does not become a pile of disconnected experiments.",
    ]
    return "<ol>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ol>"


def buying_recommendation(left: str, right: str, verdict: str) -> str:
    return "".join(
        f"<p>{paragraph}</p>"
        for paragraph in [
            verdict,
            f"If you are buying for yourself, start with a monthly plan or trial and run real work through both products. If you are buying for a team, do not skip onboarding and governance. A tool that one expert user loves may fail if the rest of the team cannot repeat the workflow.",
            f"The final decision should be based on evidence from your own tasks. Compare {left} and {right} using the same source material, the same success criteria, and the same reviewer. Keep the winner only if it produces useful output after review and reduces the total effort required to ship the work.",
            "This page includes affiliate-style links and internal review links, but the recommendation is intentionally conditional. The best choice depends on workflow fit, current pricing, policy requirements, and the cost of switching. Verify every important claim on the official vendor website before purchase.",
        ]
    )


def related_comparison_links(current_slug: str) -> str:
    links = []
    for item in COMPARISONS:
        slug = str(item["slug"])
        if slug == current_slug:
            continue
        links.append(f"<li><a href='/comparisons/{html.escape(slug)}/'>{html.escape(str(item['left']))} vs {html.escape(str(item['right']))}</a></li>")
    return "".join(links[:6])


def safe_review_url(output: Path, tool: str) -> str:
    slug = slugify(tool)
    if (output / "review" / slug / "index.html").exists():
        return review_url(tool)
    return "/reviews/"


def go_url(tool: str, offers: dict[str, dict], fallback: str) -> str:
    slug = slugify(tool)
    if slug in offers:
        return f"/go/{slug}/"
    return fallback
