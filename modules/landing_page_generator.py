from __future__ import annotations

import html
import json
import re
from datetime import date

import pandas as pd
from jinja2 import Template

from config import settings
from modules.tracking_config import analytics_snippet
from modules.affiliate_links import link_for_brand, load_affiliate_links


REVIEW_CONTENT = {
    "gamma": {
        "summary": "Gamma is useful for people who need to turn ideas into polished presentations, documents, or simple web-style pages without spending hours on layout work.",
        "what": "Gamma is an AI-assisted creation tool for decks, documents, and visual explainers. It is often a good fit when the main job is communicating an idea clearly rather than designing every slide from scratch.",
        "features": ["AI-assisted deck and document drafting.", "Flexible layouts for presentations, proposals, and explainers.", "A web-first reading experience that can be easier to share than traditional slide files.", "Templates and editing tools for faster iteration."],
        "pros": ["Fast first draft workflow for presentations and content outlines.", "Clean visual output for non-designers.", "Useful for founders, teachers, marketers, and consultants."],
        "cons": ["Final quality still depends on human editing and source material.", "Not a full replacement for advanced design tools.", "Pricing and workspace limits should be checked on the official site."],
        "who": "Gamma is best for creators, startup teams, educators, and operators who regularly explain ideas and want a faster path from outline to presentable page.",
        "alternatives": ["Canva", "Beautiful.ai", "Tome", "Google Slides"],
        "verdict": "Gamma is worth reviewing if your workflow includes frequent presentations or proposal-style content. It should be tested for output quality and team workflow fit before committing.",
        "faq": ["Is Gamma good for presentations?", "Can Gamma replace a designer?", "Does Gamma publish web pages?", "Is Gamma suitable for teams?", "Should I check Gamma pricing first?"],
    },
    "elevenlabs": {
        "summary": "ElevenLabs focuses on AI voice generation and audio workflows for creators, publishers, and teams that need natural-sounding voice output.",
        "what": "ElevenLabs is an AI voice platform used for voice generation, narration, dubbing-style workflows, and audio content production. It can help teams produce voice assets faster, but usage should follow consent, copyright, and platform rules.",
        "features": ["AI voice generation for narration and content workflows.", "Voice style controls for tone and delivery.", "Tools for audio creators, video teams, and publishers.", "API-oriented options for teams with technical workflows."],
        "pros": ["Strong category awareness in AI voice.", "Useful for creators who need repeatable audio production.", "Can reduce manual recording workload for some projects."],
        "cons": ["Voice and likeness policies must be reviewed carefully.", "Not every use case is suitable for AI-generated voice.", "Pricing and commercial usage rules should be checked before use."],
        "who": "ElevenLabs is best for video creators, educators, publishers, and product teams that need voice content and have a clear policy-compliant use case.",
        "alternatives": ["Murf AI", "PlayHT", "Descript", "WellSaid Labs"],
        "verdict": "ElevenLabs is a serious AI voice tool to compare, especially for content teams. Review the official usage rules before publishing or promoting voice workflows.",
        "faq": ["What is ElevenLabs used for?", "Can ElevenLabs be used commercially?", "Does ElevenLabs replace voice actors?", "What should I check before using AI voice?", "Is ElevenLabs good for creators?"],
    },
    "webflow-ai": {
        "summary": "Webflow AI adds AI-assisted site-building and content workflow support to Webflow's visual website platform.",
        "what": "Webflow is a website builder and visual development platform. Its AI features are positioned around helping users plan, write, and build parts of websites faster while keeping design and publishing workflows inside Webflow.",
        "features": ["Visual website design and CMS workflows.", "AI-assisted support for site planning and content tasks.", "Responsive publishing workflow for marketing sites.", "Useful for teams that want design control without a fully custom build."],
        "pros": ["Strong platform for professional marketing websites.", "Good fit for agencies, SaaS teams, and content-led businesses.", "Combines design, CMS, hosting, and publishing workflow."],
        "cons": ["There is a learning curve for advanced layouts and CMS structures.", "Costs can increase with multiple sites or advanced needs.", "AI features should be evaluated against the specific website workflow."],
        "who": "Webflow AI is best for marketers, designers, founders, and agencies that want more control than a basic site builder but less engineering overhead than custom code.",
        "alternatives": ["Framer", "Wix Studio", "Squarespace", "WordPress"],
        "verdict": "Webflow AI is worth comparing if you need a professional website workflow. It is strongest when design control and CMS flexibility matter.",
        "faq": ["What is Webflow AI?", "Is Webflow AI good for landing pages?", "Does Webflow require coding?", "Who should use Webflow?", "Should agencies compare Webflow AI?"],
    },
    "adcreative-ai": {
        "summary": "AdCreative AI is built for marketers who need faster creative concepts, ad variations, and campaign assets for testing.",
        "what": "AdCreative AI helps generate ad creative concepts and marketing visuals. It is most useful when teams need many variations to test, but performance still depends on offer quality, targeting, landing page, and campaign setup.",
        "features": ["Ad creative generation for marketing campaigns.", "Multiple creative variations for testing.", "Messaging and visual idea support for paid media teams.", "Workflow fit for ecommerce, SaaS, and agency use cases."],
        "pros": ["Can speed up creative ideation and testing.", "Useful for teams that need many visual variants.", "Helps non-design teams produce first-pass ad concepts."],
        "cons": ["Generated creative still needs human review.", "No tool can ensure campaign performance.", "Brand compliance and ad platform policy should be checked before launch."],
        "who": "AdCreative AI is best for marketers, ecommerce teams, agencies, and founders who need more ad creative variants without starting every design from scratch.",
        "alternatives": ["Canva", "Creatopy", "Predis.ai", "Designs.ai"],
        "verdict": "AdCreative AI is a practical tool to test for creative volume and workflow speed. Treat outputs as drafts that need brand and policy review.",
        "faq": ["What does AdCreative AI create?", "Can AdCreative AI improve ad testing?", "Does it guarantee ad performance?", "Who should use AdCreative AI?", "Should creatives be reviewed before launch?"],
    },
    "pipedrive-crm": {
        "summary": "Pipedrive CRM is a sales pipeline platform focused on helping teams manage deals, follow-ups, and revenue workflows.",
        "what": "Pipedrive is a CRM built around pipeline visibility and sales activity management. It can help small and mid-sized teams keep deals organized and make sales processes easier to track.",
        "features": ["Visual sales pipeline management.", "Deal tracking, activities, and follow-up workflows.", "Automation and reporting features for sales teams.", "Integrations with common business tools."],
        "pros": ["Clear pipeline-first CRM experience.", "Good fit for sales teams that want a focused workflow.", "Often easier to understand than large enterprise CRM systems."],
        "cons": ["Advanced reporting or enterprise requirements may need careful evaluation.", "Costs depend on seats, plans, and add-ons.", "Teams still need a clear sales process to get value from any CRM."],
        "who": "Pipedrive CRM is best for sales teams, agencies, consultants, and small businesses that want a practical CRM for deal tracking and follow-up discipline.",
        "alternatives": ["HubSpot", "Zoho CRM", "Freshsales", "Salesforce"],
        "verdict": "Pipedrive CRM is worth comparing for teams that want a focused sales pipeline tool. Check plan limits and integrations before choosing.",
        "faq": ["What is Pipedrive CRM best for?", "Is Pipedrive suitable for small businesses?", "Can Pipedrive replace a spreadsheet?", "What should teams check before choosing Pipedrive?", "How does Pipedrive compare with HubSpot?"],
    },
}


LANDING_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ seo_title }}</title>
  <meta name="description" content="{{ meta_description }}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{{ canonical_url }}">
  <link rel="alternate" type="application/rss+xml" title="{{ site_name }} RSS" href="{{ rss_url }}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{{ seo_title }}">
  <meta property="og:description" content="{{ meta_description }}">
  <meta property="og:url" content="{{ canonical_url }}">
  <meta property="og:site_name" content="{{ site_name }}">
  <meta property="og:image" content="{{ og_image }}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{{ seo_title }}">
  <meta name="twitter:description" content="{{ meta_description }}">
  <meta name="twitter:image" content="{{ og_image }}">
  <meta name="google-site-verification" content="{{ google_site_verification }}" />
  {{ analytics_snippet }}
  <script type="application/ld+json">{{ article_schema }}</script>
  <script type="application/ld+json">{{ review_schema }}</script>
  <script type="application/ld+json">{{ product_schema }}</script>
  <script type="application/ld+json">{{ faq_schema }}</script>
  <script type="application/ld+json">{{ breadcrumb_schema }}</script>
  <script type="application/ld+json">{{ organization_schema }}</script>
  <script type="application/ld+json">{{ person_schema }}</script>
  <script type="application/ld+json">{{ website_schema }}</script>
  <style>
    :root{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}
    *{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.6}
    .wrap{max-width:1120px;margin:0 auto;padding:0 20px}
    .nav{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
    .nav-inner{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px}
    .logo{font-weight:800;color:#0f172a;text-decoration:none}.menu{display:flex;gap:18px;flex-wrap:wrap}.menu a{color:#475569;text-decoration:none;font-size:14px}.language-switcher{display:flex;gap:8px;align-items:center;border:1px solid #dbe3ef;border-radius:999px;padding:4px 8px;background:#f8fafc;font-size:13px;white-space:nowrap}.language-switcher span{font-weight:800;color:#0f766e}.language-switcher a{color:#475569;text-decoration:none}
    .hero{padding:46px 0 18px;background:linear-gradient(180deg,#ffffff,#f7f9fc)}
    .hero-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;align-items:start}
    h1{font-size:44px;line-height:1.08;margin:12px 0 12px;letter-spacing:0}h2{font-size:26px;line-height:1.25;margin:0 0 12px;white-space:normal;overflow:visible;text-overflow:clip;word-break:normal}h3{font-size:18px;margin:0 0 8px}
    p,li{color:var(--muted)}.badge{display:inline-block;border:1px solid #a7f3d0;background:#ecfdf5;color:#047857;border-radius:999px;padding:5px 10px;font-size:13px;font-weight:700;margin-right:6px}
    .btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:12px 16px;border-radius:6px;font-weight:800;margin-right:10px}.btn.secondary{background:#e2e8f0;color:#0f172a}
    .card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px;margin:16px 0;box-shadow:0 1px 2px rgba(15,23,42,.04);max-width:100%;min-width:0;overflow-wrap:break-word}
    .media-placeholder{min-height:170px;border:1px dashed #94a3b8;border-radius:8px;background:linear-gradient(135deg,#ecfeff,#f8fafc);display:flex;align-items:center;justify-content:center;text-align:center;color:#475569;font-weight:800;padding:18px}.screenshot{width:100%;max-width:100%;height:auto;aspect-ratio:5/3;object-fit:contain;border:1px solid var(--line);border-radius:8px;display:block;background:#fff}
    .logo-placeholder{width:74px;height:74px;border-radius:16px;background:#0f766e;color:#fff;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;margin-bottom:12px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;min-width:0}.score{font-size:42px;font-weight:800;color:var(--accent);line-height:1}
    .rating-summary{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:16px;align-items:start}.rating-summary h2{margin-top:0}.rating-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start;border-top:1px solid #edf2f7;padding:9px 0;color:#475569}.rating-row:first-of-type{border-top:0}.rating-row strong{text-align:right;overflow-wrap:anywhere}
    table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}th{background:#f1f5f9;color:#334155}
    .review-layout{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;align-items:start}.review-layout>.breadcrumb{grid-column:1}.review-layout>.toc{grid-column:1;grid-row:auto;position:relative;top:auto;max-height:none;overflow:visible;z-index:1}.review-layout>div{grid-column:1;grid-row:auto;min-width:0}.toc{position:relative;max-width:100%}.toc a{display:block;color:#475569;text-decoration:none;padding:8px 0;border-bottom:1px solid #edf2f7;line-height:1.35;overflow-wrap:anywhere}.breadcrumb{font-size:14px;color:#64748b;margin-bottom:14px}.share a{display:inline-block;margin:0 8px 8px 0;color:#0f766e;font-weight:700}.author-box{display:grid;grid-template-columns:1fr;gap:8px}.related a{display:inline-block;margin:0 8px 8px 0;color:#0f766e;font-weight:700}.trust{border-left:4px solid var(--warn);background:#fff7ed}.pros{color:#166534}.cons{color:#991b1b}.note{font-size:14px;color:#7c2d12}.search{width:100%;padding:12px 14px;border:1px solid #cbd5e1;border-radius:8px;margin:8px 0 18px}details{border-top:1px solid #e6edf5;padding:12px 0}summary{cursor:pointer;font-weight:800;color:#334155}
    footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0;text-decoration:none;margin-right:14px}footer p{color:#cbd5e1}
    @media (max-width:900px){.rating-summary{grid-template-columns:1fr}.review-layout{grid-template-columns:1fr}.review-layout>.breadcrumb,.review-layout>.toc,.review-layout>div{grid-column:1;grid-row:auto}.review-layout>.toc,.toc{position:relative;top:auto;max-height:none;overflow:visible}}@media (max-width:760px){h1{font-size:34px}.nav-inner{height:auto;padding:14px 0;align-items:flex-start;flex-direction:column}.language-switcher{margin-top:6px}.btn{display:block;text-align:center;margin:8px 0}.grid{grid-template-columns:1fr}.rating-row{grid-template-columns:1fr}.rating-row strong{text-align:left}}
  </style>
</head>
<body>
  <nav class="nav"><div class="wrap nav-inner"><a class="logo" href="/">{{ site_name }}</a><div class="menu"><a href="/">Home</a><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/about/">About</a><a href="/contact/">Contact</a></div><div class="language-switcher" aria-label="Language switcher"><span>English</span><a href="/vi/">Ti?ng Vi?t</a></div></div><div class="wrap"><p class="note">Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></div></nav>
  <header class="hero"><div class="wrap hero-grid">
    <div>
      <span class="badge">Review</span><span class="badge">AI Tool</span><span class="badge">SaaS</span>
      <div class="logo-placeholder" aria-label="{{ brand }} logo placeholder">{{ brand_initial }}</div>
      <h1>{{ brand }} Review</h1>
      <p>{{ short_description }}</p>
      <p><strong>Short answer:</strong> {{ short_answer }}</p>
      <p><a class="btn" href="{{ cta_url }}" rel="nofollow sponsored">Visit Official Website</a><a class="btn secondary" href="#pricing">Verify Current Pricing</a></p>
      {% if pending_note %}<p class="note">{{ pending_note }}</p>{% endif %}
    </div>
    <aside class="card rating-summary">
      <div>{{ screenshot_html }}</div>
      <div>
        <h2>Rating Summary</h2>
        <div class="score">{{ overall_score }}/100</div>
        <div class="rating-row"><span>Ease of use</span><strong>{{ ease_score }}/10</strong></div>
        <div class="rating-row"><span>Pricing</span><strong>{{ pricing_score }}/10</strong></div>
        <div class="rating-row"><span>Features</span><strong>{{ feature_score }}/10</strong></div>
        <div class="rating-row"><span>Best for</span><strong>{{ best_for }}</strong></div>
      </div>
    </aside>
  </div></header>
  <main class="wrap review-layout" id="review">
    <aside class="card toc"><h2>Contents</h2><a href="#overview">Overview</a><a href="#features">Features</a><a href="#pros-cons">Pros and Cons</a><a href="#pricing">Pricing</a><a href="#who">Who Should Use It</a><a href="#alternatives">Alternatives</a><a href="#faq">FAQ</a><a href="#verdict">Final Verdict</a></aside>
    <div>
    <nav class="breadcrumb"><a href="/">Home</a> / <a href="/reviews/">Reviews</a> / {{ brand }} Review</nav>
    <section class="card" id="overview"><h2>Overview</h2><p>{{ intro_summary }}</p><p><strong>Last updated:</strong> {{ last_updated }} | {{ reading_time }} min read</p>{{ share_buttons }}</section>
    <section class="card trust"><strong>This review is for research purposes only.</strong><br>We may earn commission if you purchase through our links. This does not change your price.</section>
    <section class="card trust"><strong>Affiliate disclosure:</strong> Some links may be affiliate links. We may earn a commission at no extra cost to you.</section>
    <section class="grid">
      <div class="card">{{ screenshot_html }}</div>
      <div class="card"><h2>Best for</h2><ul>{% for item in best_for_bullets %}<li>{{ item }}</li>{% endfor %}</ul><h2>Not best for</h2><ul>{% for item in not_best_for_bullets %}<li>{{ item }}</li>{% endfor %}</ul></div>
    </section>
    <section class="grid">
      <div class="card"><h2>When to use it</h2><p>{{ when_to_use }}</p></div>
      <div class="card"><h2>When not to use it</h2><p>{{ when_not_to_use }}</p></div>
      <div class="card"><h2>Workflow fit</h2><p>{{ workflow_fit }}</p></div>
    </section>
    <section class="card"><h2>Best audience</h2><p>{{ best_audience }}</p></section>
    <section class="grid">
      <div class="card"><h2>What problem does this tool solve?</h2><p>{{ what_is }}</p></div>
      <div class="card" id="who"><h2>Who should consider it?</h2><p>{{ who_for }}</p></div>
    </section>
    <section class="card" id="features"><h2>Notable features</h2><ul>{% for item in features %}<li>{{ item }}</li>{% endfor %}</ul></section>
    <section class="grid">
      <div class="card"><h2>Standout strengths</h2><ul class="pros">{% for item in standout_strengths %}<li>{{ item }}</li>{% endfor %}</ul></div>
      <div class="card"><h2>Friction points</h2><ul class="cons">{% for item in friction_points %}<li>{{ item }}</li>{% endfor %}</ul></div>
    </section>
    <section class="grid" id="pros-cons">
      <div class="card"><h2>Pros</h2><ul class="pros">{% for item in pros %}<li>{{ item }}</li>{% endfor %}</ul></div>
      <div class="card"><h2>Cons / limitations</h2><ul class="cons">{% for item in cons %}<li>{{ item }}</li>{% endfor %}</ul></div>
    </section>
    <section class="card"><h2>Pros and cons table</h2>
      <table><thead><tr><th>Pros</th><th>Cons</th></tr></thead><tbody>{{ pros_cons_rows }}</tbody></table>
    </section>
    <section class="card"><h2>Score explanation</h2><p>{{ score_explanation }}</p><table><tbody><tr><td>Usability</td><td>{{ usability_reason }}</td></tr><tr><td>Pricing</td><td>{{ pricing_reason }}</td></tr><tr><td>Workflow fit</td><td>{{ workflow_reason }}</td></tr><tr><td>Integrations</td><td>{{ integration_reason }}</td></tr></tbody></table></section>
    <section class="card" id="pricing"><h2>Pricing note</h2><p><strong>Verify current pricing on the official website.</strong> Pricing, trials, plan limits, and cancellation terms can change over time.</p></section>
    <section class="card"><h2>Pricing summary</h2><p>{{ pricing_summary }}</p></section>
    <section class="card"><h2>Affiliate link field</h2><p><strong>Status:</strong> {{ affiliate_link_status }}</p><p><strong>CTA URL used now:</strong> <a href="{{ cta_url }}" rel="nofollow sponsored">{{ cta_url_label }}</a></p><p class="note">Replace this with an approved affiliate link only after the affiliate program approves your account. Do not use fake affiliate links.</p></section>
    <section class="card" id="comparisons"><h2>Comparison table</h2>
      <table><thead><tr><th>Tool</th><th>Best for</th><th>Pricing type</th><th>Pros</th><th>Cons</th></tr></thead><tbody>
        <tr><td>{{ brand }}</td><td>{{ best_for }}</td><td>Verify on the official website</td><td>{{ comparison_pro }}</td><td>{{ comparison_con }}</td></tr>
        <tr><td>Alternative 1</td><td>Teams comparing {{ niche }} options</td><td>Varies</td><td>May fit different workflows</td><td>Requires separate verification</td></tr>
        <tr><td>Alternative 2</td><td>Budget-sensitive buyers</td><td>Varies</td><td>May offer simpler entry plan</td><td>Feature depth may differ</td></tr>
      </tbody></table>
    </section>
    <section class="card" id="alternatives"><h2>Best alternatives</h2><ul>{% for item in alternatives %}<li>{{ item }}</li>{% endfor %}</ul><p>Good alternatives depend on your budget, workflow and required integrations. Compare at least two or three tools before buying.</p></section>
    <section class="card"><h2>How we tested</h2><ul>{% for item in how_tested %}<li>{{ item }}</li>{% endfor %}</ul></section>
    <section class="card"><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p><p>We may earn a commission if this site later uses an approved affiliate link for {{ brand }}. If affiliate approval is still pending, the button points to the official website instead of a tracked affiliate link.</p></section>
    <section class="card" id="faq"><h2>FAQ</h2>
      {% for faq in faq_items %}<details><summary>{{ faq.question }}</summary><p>{{ faq.answer }}</p></details>{% endfor %}
    </section>
    <section class="card related"><h2>Internal links for deeper research</h2><h3>Related comparisons</h3>{% for item in related_comparisons %}<a href="/comparisons/{{ item.slug }}/">{{ item.title }}</a>{% endfor %}<h3>Alternatives and similar tools</h3>{% for item in related_reviews %}<a href="/{{ item.slug }}/">{{ item.brand }}</a>{% endfor %}</section>
    <section class="card author-box"><h2>Author</h2><p><strong>Nguyen Quoc Tuan</strong><br>Independent AI & SaaS Researcher</p><p>Researching AI tools, SaaS software, automation systems, and productivity workflows.</p><h3>Research methodology</h3><ul><li>Tested feature review</li><li>Public pricing review</li><li>UI evaluation</li><li>Workflow comparison</li><li>User feedback research</li></ul></section>
    <section class="card trust"><h2>Get new AI tool reviews and comparisons.</h2><p>Join the research list for new AI/SaaS review updates. No backend is connected yet; this email field is ready for a future email provider.</p><form><input class="search" type="email" placeholder="email address" aria-label="Email address"><button class="btn" type="button">Notify me</button></form></section>
    <section class="card" id="verdict"><h2>Final verdict</h2><p>{{ verdict }}</p><p><a class="btn" href="/comparisons/">Compare now</a><a class="btn" href="{{ cta_url }}" rel="nofollow sponsored">Visit Official Website</a><a class="btn secondary" href="#alternatives">See alternatives</a></p></section>
    </div>
  </main>
  <footer><div class="wrap"><p><strong>{{ site_name }}</strong></p><p>Contact: <a href="mailto:{{ contact_email }}">{{ contact_email }}</a></p><a href="/privacy/">Privacy Policy</a><a href="/terms/">Terms</a><a href="/disclosure/">Disclosure</a><a href="/about/">About</a><a href="/contact/">Contact</a><p>&copy; 2026 {{ site_name }}.</p><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p><p>Reviews are for research purposes only.</p></div></footer>
</body>
</html>
"""


def generate_landing_pages(offer_scores: pd.DataFrame, angles: dict[str, dict]) -> pd.DataFrame:
    rows = []
    template = Template(LANDING_TEMPLATE)
    affiliate_links = load_affiliate_links()
    for _, offer in offer_scores.iterrows():
        if offer.get("compliance_status") == "BLOCKED":
            continue
        slug = slugify(str(offer.get("brand_name", "")))
        out_dir = settings.landing_output_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "index.html"
        html_text = template.render(**build_context(offer, affiliate_links))
        path.write_text(html_text, encoding="utf-8")
        rows.append(
            {
                "offer_id": offer.get("offer_id", ""),
                "brand_name": offer.get("brand_name", ""),
                "landing_page": str(path),
                "landing_page_url": path.resolve().as_uri(),
                "status": "created",
            }
        )
    return pd.DataFrame(rows)


def build_context(offer: pd.Series, affiliate_links: pd.DataFrame | None = None) -> dict:
    brand = str(offer.get("brand_name", ""))
    slug = slugify(brand)
    niche = str(offer.get("niche", "software"))
    score = int(float(offer.get("total_score") or 0))
    risk = str(offer.get("risk_level", "Medium"))
    competition = str(offer.get("competition", "Medium"))
    link = link_for_brand(brand, affiliate_links if affiliate_links is not None else pd.DataFrame())
    content = review_content_for(brand, niche, offer)
    canonical = canonical_url(slug)
    faq_items = faq_items_for(brand, content)
    meta_description = f"Research-style review of {brand}: workflow fit, strengths, limitations, pricing notes, alternatives, FAQ, and affiliate disclosure."
    return {
        "brand": html.escape(brand),
        "site_name": html.escape(settings.site_name),
        "contact_email": html.escape(settings.contact_email or "contact@smileaireviewhub.com"),
        "rss_url": html.escape(f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/rss.xml", quote=True),
        "google_site_verification": html.escape(settings.google_site_verification, quote=True),
        "analytics_snippet": analytics_snippet(),
        "seo_title": html.escape(f"{brand} Review: Features, Pros, Cons, Pricing Notes"),
        "meta_description": html.escape(meta_description),
        "canonical_url": html.escape(canonical, quote=True),
        "og_image": html.escape(f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/assets/og/{slug}.svg", quote=True),
        "article_schema": json.dumps(article_schema(brand, meta_description, canonical), ensure_ascii=False),
        "review_schema": json.dumps(review_schema(brand, score, meta_description, canonical), ensure_ascii=False),
        "product_schema": json.dumps(product_schema(brand, niche, score, meta_description, canonical), ensure_ascii=False),
        "faq_schema": json.dumps(faq_schema(faq_items), ensure_ascii=False),
        "breadcrumb_schema": json.dumps(breadcrumb_schema(brand, canonical), ensure_ascii=False),
        "organization_schema": json.dumps(organization_schema(), ensure_ascii=False),
        "person_schema": json.dumps(person_schema(), ensure_ascii=False),
        "website_schema": json.dumps(website_schema(), ensure_ascii=False),
        "niche": html.escape(niche),
        "article": article_for(niche),
        "brand_initial": html.escape((brand[:1] or "A").upper()),
        "cta_url": html.escape(str(link.get("cta_url") or offer.get("website") or "#"), quote=True),
        "pending_note": html.escape(str(link.get("pending_note", ""))),
        "overall_score": score,
        "ease_score": score_to_ten(score + 4),
        "pricing_score": score_to_ten(score - (8 if competition == "High" else 2)),
        "feature_score": score_to_ten(score + 2),
        "best_for": html.escape(best_for(niche)),
        "best_for_bullets": best_for_bullets(brand, niche),
        "not_best_for_bullets": not_best_for_bullets(niche),
        "short_description": html.escape(short_description(brand, niche)),
        "short_answer": html.escape(short_answer_for(brand, niche, score, risk)),
        "intro_summary": html.escape(editorial_summary(brand, niche, score, risk)),
        "what_is": html.escape(human_what_is(brand, niche)),
        "who_for": html.escape(content["who"]),
        "when_to_use": html.escape(when_to_use(brand, niche)),
        "when_not_to_use": html.escape(when_not_to_use(brand, niche)),
        "workflow_fit": html.escape(workflow_fit(brand, niche)),
        "best_audience": html.escape(best_audience(brand, niche)),
        "features": editorial_features(brand, niche, content),
        "pros": content["pros"],
        "cons": content["cons"],
        "standout_strengths": standout_strengths(brand, niche, content),
        "friction_points": friction_points(brand, niche, content),
        "pros_cons_rows": pros_cons_rows(content["pros"], content["cons"]),
        "score_explanation": html.escape(score_explanation(brand, score, risk, competition)),
        "usability_reason": html.escape(usability_reason(score)),
        "pricing_reason": html.escape(pricing_reason(competition)),
        "workflow_reason": html.escape(workflow_reason(niche)),
        "integration_reason": html.escape(integration_reason(niche)),
        "alternatives": content["alternatives"],
        "not_best_for": html.escape(not_best_for(niche)),
        "pricing_summary": html.escape("Pricing can change. Use this review as a research starting point and confirm the latest plan limits, trial terms, cancellation terms, and commercial usage rules on the official website."),
        "affiliate_link_status": html.escape("Approved affiliate link" if link.get("approved") else "Affiliate link pending approval"),
        "cta_url_label": html.escape(str(link.get("cta_url") or offer.get("website") or "#")),
        "how_tested": [
            "Reviewed the public product positioning and feature set.",
            "Compared the tool against category alternatives.",
            "Checked pricing and policy areas that require manual verification.",
            "Evaluated workflow fit for realistic business use cases.",
            "Marked affiliate approval and traffic policy as pending when not verified.",
        ],
        "faq_items": faq_items,
        "related_reviews": related_reviews_for(brand, niche),
        "related_comparisons": related_comparisons_for(brand),
        "screenshot_html": screenshot_html(slug, brand),
        "share_buttons": share_buttons(slug, brand),
        "reading_time": 8 if brand in {"Gamma", "ElevenLabs", "Webflow AI", "AdCreative AI", "Pipedrive CRM"} else 5,
        "last_updated": date.today().isoformat(),
        "comparison_pro": html.escape("Clear use case fit and useful research signals."),
        "comparison_con": html.escape("Policy and pricing should be verified on the official website."),
        "direct_linking_note": html.escape("Use a review landing page unless the affiliate terms clearly allow direct linking." if not truthy(offer.get("direct_linking_allowed")) else "Direct linking appears allowed in the current data, but verify the official terms first."),
        "trademark_note": html.escape("Do not bid on trademark or brand keywords unless the affiliate terms explicitly allow it." if not truthy(offer.get("brand_bidding_allowed")) else "Brand bidding appears allowed in the current data, but verify before launching ads."),
        "verdict": html.escape(content["verdict"]),
    }



def review_content_for(brand: str, niche: str, offer: pd.Series) -> dict:
    content = REVIEW_CONTENT.get(slugify(brand))
    if content:
        return content
    return {
        "summary": short_description(brand, niche),
        "what": (
            f"{brand} belongs in the {niche} category. Instead of treating it as a feature checklist, "
            "this review looks at where the tool may fit in a real workflow, who should test it first, "
            "and which pricing, policy, and integration details need verification before buying or promoting it."
        ),
        "features": features_for(niche),
        "pros": pros_for(offer),
        "cons": cons_for(offer),
        "who": who_for(niche),
        "alternatives": ["Compare category leaders", "Check direct competitors", "Review budget-friendly options"],
        "faq": default_faq_questions(brand),
        "verdict": verdict(brand, int(float(offer.get("total_score") or 0)), str(offer.get("risk_level", "Medium"))),
    }


def faq_items_for(brand: str, content: dict) -> list[dict[str, str]]:
    questions = (content.get("faq") or []) + default_faq_questions(brand)
    seen = []
    for question in questions:
        if question not in seen:
            seen.append(question)
    answers = faq_answer_map(brand)
    return [{"question": html.escape(q), "answer": html.escape(answers[idx % len(answers)])} for idx, q in enumerate(seen[:8])]


def related_reviews_for(brand: str, niche: str) -> list[dict[str, str]]:
    related_map = {
        "gamma": [("Webflow AI", "webflow-ai"), ("AdCreative AI", "adcreative-ai"), ("Notion", "notion")],
        "elevenlabs": [("Synthesia", "synthesia"), ("AdCreative AI", "adcreative-ai"), ("Gamma", "gamma")],
        "pipedrive-crm": [("HubSpot", "hubspot"), ("ActiveCampaign", "activecampaign"), ("Make", "make")],
        "webflow-ai": [("Gamma", "gamma"), ("Canva", "canva"), ("AdCreative AI", "adcreative-ai")],
        "adcreative-ai": [("Canva", "canva"), ("Gamma", "gamma"), ("Webflow AI", "webflow-ai")],
    }
    items = related_map.get(slugify(brand), [("Surfer SEO", "surfer-seo"), ("Make", "make"), ("ActiveCampaign", "activecampaign")])
    return [{"brand": html.escape(name), "slug": slug} for name, slug in items if name != brand]


def default_faq_questions(brand: str) -> list[str]:
    return [
        f"Where should I verify current {brand} pricing?",
        f"Which {brand} alternatives are worth comparing?",
        f"Should beginners use {brand}?",
        f"Does {brand} offer a refund policy or trial?",
        f"Which workflows does {brand} integrate with?",
        f"Should teams use {brand} for shared work?",
    ]


def editorial_summary(brand: str, niche: str, score: int, risk: str) -> str:
    return (
        f"This review evaluates {brand} from a practical research angle: which {niche} workflow it may fit, "
        f"which strengths matter, which limitations need checking, and whether it deserves a place on your shortlist. "
        f"With a current score of {score}/100 and a {risk} risk signal, the responsible approach is to treat this as a first-pass filter, "
        "then verify pricing, integrations, usage rights, and official terms before buying or promoting it."
    )


def human_what_is(brand: str, niche: str) -> str:
    return (
        f"{brand} is an option in the {niche} category. The real value is not simply having many features; "
        "it is whether the tool makes a specific workflow faster, clearer, or easier to repeat. This review therefore "
        "places the product in a day-to-day usage context instead of only listing feature claims."
    )


def editorial_features(brand: str, niche: str, content: dict) -> list[str]:
    base = [
        f"Supports one or more steps in a {niche} workflow.",
        f"Can be tested on a small workflow before rolling {brand} out more broadly.",
        "Pricing, plan limits, commercial usage rights, and integrations should be checked on the official website.",
    ]
    extras = list(content.get("features", []))[:3]
    return base + extras


def faq_answer_map(brand: str) -> list[str]:
    return [
        f"Pricing, trial terms, and plan limits for {brand} can change. Use the official website as the final source before buying.",
        "Compare at least two or three tools in the same category to understand workflow, pricing, integration, and commercial usage differences.",
        "Beginners can test it if they have a clear use case. A safer approach is to try one small workflow before moving an entire process into a new tool.",
        "Refund, cancellation, and trial policies should be checked in the official terms because every vendor handles them differently.",
        "Integrations only matter if they match the tools you already use every day. Check app integrations, API support, or import/export options before rollout.",
        "Teams should use it when there is a clear owner, an output review process, and a reasonable budget. Do not buy only because a tool is popular.",
        "For affiliate or paid traffic, verify disclosure rules, trademark bidding, direct linking, and traffic policy before promotion.",
        "This is research content, not a promise of business results or advertising performance.",
    ]


def when_to_use(brand: str, niche: str) -> str:
    return f"Consider {brand} when you already have a specific {niche} workflow to improve, such as speeding up content work, organizing leads, automating repeated steps, or standardizing a team process."


def when_not_to_use(brand: str, niche: str) -> str:
    return f"Do not rush into {brand} if you have not defined the problem, have not checked current pricing, or need an absolutely verified recommendation for every {niche} situation."


def workflow_fit(brand: str, niche: str) -> str:
    return f"The best workflow is to start small: choose one {niche} use case, produce a sample output with {brand}, compare it with your current process, and only then decide whether it belongs in the main workflow."


def best_audience(brand: str, niche: str) -> str:
    return f"{brand} is best for people actively comparing {niche} tools, working with a small test budget, and willing to verify pricing, plan limits, integrations, and official terms before committing."


def standout_strengths(brand: str, niche: str, content: dict) -> list[str]:
    items = list(content.get("pros", []))[:2]
    items.append(f"Useful as a shortlist candidate when researching the {niche} category.")
    items.append(f"Can be a starting point for comparing {brand} with similar alternatives.")
    return items


def friction_points(brand: str, niche: str, content: dict) -> list[str]:
    items = list(content.get("cons", []))[:2]
    items.append("Current pricing and official terms need to be checked before making a decision.")
    items.append("Affiliate or ad use requires policy verification instead of relying only on review content.")
    return items


def pros_cons_rows(pros: list[str], cons: list[str]) -> str:
    size = max(len(pros), len(cons), 1)
    rows = []
    for idx in range(size):
        left = html.escape(pros[idx]) if idx < len(pros) else ""
        right = html.escape(cons[idx]) if idx < len(cons) else ""
        rows.append(f"<tr><td>? {left}</td><td>? {right}</td></tr>")
    return "".join(rows)


def score_explanation(brand: str, score: int, risk: str, competition: str) -> str:
    return f"The {score}/100 score for {brand} is not a quality guarantee. It reflects usability signals, workflow fit, pricing risk, competition, and current policy risk. With risk marked as {risk} and competition marked as {competition}, a small test and manual verification are still recommended."


def usability_reason(score: int) -> str:
    return "The usability signal looks relatively strong." if score >= 80 else "The real user experience should be checked before making it part of a core workflow."


def pricing_reason(competition: str) -> str:
    return "Pricing needs verification; high competition can increase promotion costs." if competition == "High" else "Pricing still needs to be checked on the official website before buying."


def workflow_reason(niche: str) -> str:
    return f"The workflow score is based on whether the tool can support repeatable {niche} tasks instead of only looking good on a feature list."


def integration_reason(niche: str) -> str:
    return f"Integrations should be checked against your real stack, especially if {niche} work involves team workflows or automation."

def related_comparisons_for(brand: str) -> list[dict[str, str]]:
    key = slugify(brand)
    mapping = {
        "gamma": [("canva-vs-gamma", "Canva vs Gamma"), ("chatgpt-vs-gemini", "ChatGPT vs Gemini")],
        "canva": [("canva-vs-gamma", "Canva vs Gamma")],
        "elevenlabs": [("elevenlabs-vs-murf", "ElevenLabs vs Murf"), ("elevenlabs-vs-playht", "ElevenLabs vs PlayHT")],
        "pipedrive-crm": [("hubspot-vs-salesforce", "HubSpot vs Salesforce"), ("notion-vs-clickup", "Notion vs ClickUp")],
        "hubspot": [("hubspot-vs-salesforce", "HubSpot vs Salesforce"), ("notion-vs-clickup", "Notion vs ClickUp")],
        "make": [("make-vs-zapier", "Make vs Zapier")],
        "surfer-seo": [("semrush-vs-ahrefs", "Semrush vs Ahrefs"), ("jasper-vs-copyai", "Jasper vs Copy.ai")],
        "webflow-ai": [("framer-vs-webflow", "Framer vs Webflow")],
        "webflow": [("framer-vs-webflow", "Framer vs Webflow")],
    }
    items = mapping.get(key, [("chatgpt-vs-gemini", "ChatGPT vs Gemini"), ("make-vs-zapier", "Make vs Zapier")])
    return [{"slug": slug, "title": html.escape(title)} for slug, title in items]


def screenshot_html(slug: str, brand: str) -> str:
    source = settings.base_dir / "assets" / "screenshots" / f"{slug}.png"
    if source.exists():
        return f'<img class="screenshot" loading="lazy" src="/assets/screenshots/{html.escape(slug)}.png" alt="{html.escape(brand)} research visual with editorial score and review signals" width="1200" height="720">'
    return f'<div class="media-placeholder" role="img" aria-label="{html.escape(brand)} research visual">Research visual<br>Add image at assets/screenshots/{html.escape(slug)}.png</div>'


def canonical_url(slug: str) -> str:
    base = settings.base_site_url or settings.site_domain or "https://yourdomain.com"
    return f"{base.rstrip('/')}/{slug}/"


def share_buttons(slug: str, brand: str) -> str:
    url = f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/{slug}/"
    title = f"{brand} Review"
    encoded_url = html.escape(url, quote=True)
    encoded_title = html.escape(title.replace(" ", "%20"), quote=True)
    return f"<p class='share'><strong>Share:</strong> <a href='https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}'>LinkedIn</a> <a href='https://www.pinterest.com/pin/create/button/?url={encoded_url}&description={encoded_title}'>Pinterest</a> <a href='https://www.facebook.com/sharer/sharer.php?u={encoded_url}'>Facebook</a> <a href='https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_title}'>X/Twitter</a></p>"


def article_schema(brand: str, description: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{brand} Review",
        "description": description,
        "url": canonical,
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan", "jobTitle": "Independent AI & SaaS Researcher"},
        "publisher": {"@type": "Organization", "name": settings.site_name},
        "dateModified": date.today().isoformat(),
    }


def review_schema(brand: str, score: int, description: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Review",
        "itemReviewed": {"@type": "SoftwareApplication", "name": brand, "applicationCategory": "BusinessApplication"},
        "name": f"{brand} Review",
        "description": description,
        "url": canonical,
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
        "reviewRating": {"@type": "Rating", "ratingValue": max(1, min(5, round(score / 20, 1))), "bestRating": 5, "worstRating": 1},
        "publisher": {"@type": "Organization", "name": settings.site_name},
    }


def product_schema(brand: str, niche: str, score: int, description: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": brand,
        "description": description,
        "url": canonical,
        "category": niche,
        "brand": {"@type": "Brand", "name": brand},
        "review": {
            "@type": "Review",
            "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
            "reviewRating": {"@type": "Rating", "ratingValue": max(1, min(5, round(score / 20, 1))), "bestRating": 5, "worstRating": 1},
            "reviewBody": "Research-style editorial review focused on workflow fit, pricing verification, alternatives, and affiliate disclosure.",
        },
    }


def organization_schema() -> dict:
    base = settings.base_site_url or settings.site_domain or "https://yourdomain.com"
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": settings.site_name,
        "url": base.rstrip("/") + "/",
        "email": settings.contact_email or "",
        "contactPoint": [
            {"@type": "ContactPoint", "email": settings.contact_email or "", "contactType": "business inquiries"},
            {"@type": "ContactPoint", "email": settings.admin_email or "", "contactType": "partnership requests"},
        ],
    }


def person_schema() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Nguyen Quoc Tuan",
        "jobTitle": "Independent AI & SaaS Researcher",
        "description": "Researching AI tools, SaaS software, automation systems, and productivity workflows.",
    }


def website_schema() -> dict:
    base = settings.base_site_url or settings.site_domain or "https://yourdomain.com"
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": settings.site_name,
        "url": base.rstrip("/") + "/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": base.rstrip("/") + "/reviews/?q={search_term_string}",
            "query-input": "required name=search_term_string",
        },
    }


def faq_schema(faq_items: list[dict[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": item["question"], "acceptedAnswer": {"@type": "Answer", "text": item["answer"]}}
            for item in faq_items
        ],
    }


def breadcrumb_schema(brand: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": settings.base_site_url or settings.site_domain or "https://yourdomain.com"},
            {"@type": "ListItem", "position": 2, "name": "Reviews", "item": f"{(settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/')}/reviews/"},
            {"@type": "ListItem", "position": 3, "name": f"{brand} Review", "item": canonical},
        ],
    }


def score_to_ten(value: int) -> str:
    return str(max(1, min(10, round(value / 10, 1))))


def best_for(niche: str) -> str:
    mapping = {
        "AI SEO": "content teams and SEO-focused marketers",
        "Automation": "operators automating repeat workflows",
        "AI Meeting": "busy teams managing calendar and meeting workflows",
        "Email Marketing": "marketers building email automation",
        "AI Video": "creators and teams producing video content",
        "AI Voice": "creators testing voice and audio workflows",
        "AI Design": "design and marketing teams",
        "CRM": "sales teams managing leads and pipelines",
        "Productivity": "teams improving daily workflows",
    }
    return mapping.get(niche, "teams comparing SaaS tools")



def best_for_bullets(brand: str, niche: str) -> list[str]:
    return [
        f"Readers comparing {brand} with other {niche} tools in the same category.",
        "Teams that want a research-style review before signing up.",
        "Buyers willing to check current pricing and official terms before purchase.",
    ]


def not_best_for_bullets(niche: str) -> list[str]:
    return [
        f"Buyers who want a fully verified {niche} recommendation without checking vendor terms.",
        "Anyone expecting guaranteed results or guaranteed ROI.",
        "Paid campaigns that have not checked affiliate policy, trademark bidding, and direct linking rules.",
    ]


def article_for(text: str) -> str:
    return "an" if text.strip().lower().startswith(("a", "e", "i", "o", "u")) else "a"


def short_description(brand: str, niche: str) -> str:
    return f"A practical review of {brand} for readers comparing {niche} tools: strengths, limitations, alternatives, workflow fit, and policy details to verify."


def short_answer_for(brand: str, niche: str, score: int, risk: str) -> str:
    if score >= 82 and risk != "High":
        return f"{brand} deserves a place on your {niche} shortlist if current pricing, integrations, and official policies match your workflow."
    return f"{brand} should be treated as a research candidate; verify pricing, affiliate terms, and workflow fit before relying on it."


def not_best_for(niche: str) -> str:
    return f"Not ideal for buyers who need a fully verified {niche} recommendation without checking current vendor terms, pricing, and usage policies."


def who_for(niche: str) -> str:
    return f"Best for readers comparing {niche} options who want to understand use cases, limitations, pricing risk, and alternatives before signing up."

def features_for(niche: str) -> list[str]:
    return [
        f"Core workflow support for {niche}.",
        "Useful for review, comparison and product research workflows.",
        "Requires official pricing and policy verification before paid promotion.",
    ]


def pros_for(offer: pd.Series) -> list[str]:
    pros = ["Clear category fit for comparison content."]
    if truthy(offer.get("recurring")):
        pros.append("Recurring commission signal in the current data.")
    if str(offer.get("buyer_intent_label", "")) == "High":
        pros.append("High buyer intent signal.")
    if float(offer.get("estimated_roi") or 0) > 0:
        pros.append("Positive estimated ROI signal, pending real campaign data.")
    return pros


def cons_for(offer: pd.Series) -> list[str]:
    cons = ["Pricing and terms must be checked on the official website."]
    if not truthy(offer.get("direct_linking_allowed")):
        cons.append("Direct affiliate linking should be avoided unless terms allow it.")
    if not truthy(offer.get("brand_bidding_allowed")):
        cons.append("Trademark bidding should be avoided.")
    if str(offer.get("data_confidence", "")) == "LOW":
        cons.append("Current data confidence is low and needs manual verification.")
    return cons


def verdict(brand: str, score: int, risk: str) -> str:
    if score >= 80 and risk != "High":
        return f"{brand} looks worth deeper testing with a small budget after manual policy verification."
    if score >= 60:
        return f"{brand} may be worth monitoring, but verify pricing, payout and traffic policy before running ads."
    return f"{brand} should stay on the watchlist until stronger data is available."


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "allowed"}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "offer"
