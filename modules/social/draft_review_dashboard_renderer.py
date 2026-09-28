from __future__ import annotations

import html
import json
from typing import Any


def render_review_dashboard_html(payload: dict[str, Any], *, data_json: str | None = None) -> str:
    resolved = str(payload.get("batch_date") or "")
    data_json = data_json or json.dumps(payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Social Review Dashboard - {html.escape(resolved)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{ --ink:#102033; --muted:#607086; --line:#dbe5f1; --soft:#f6f8fb; --accent:#0f766e; --warn:#a16207; --bad:#b91c1c; --good:#15803d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:#eef3f8; }}
    header {{ padding:18px 24px; background:#fff; border-bottom:1px solid var(--line); display:flex; gap:14px; align-items:flex-start; justify-content:space-between; }}
    .header-actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    h1 {{ margin:0 0 5px; font-size:26px; }}
    .muted {{ color:var(--muted); }}
    .layout {{ display:grid; grid-template-columns:minmax(280px, 340px) minmax(0, 1fr); gap:16px; padding:16px; min-height:calc(100vh - 86px); }}
    aside,.panel {{ background:#fff; border:1px solid var(--line); border-radius:8px; }}
    aside {{ overflow:auto; max-height:calc(100vh - 116px); }}
    .filters {{ position:sticky; top:0; z-index:2; background:#fff; border-bottom:1px solid var(--line); padding:12px; }}
    .filters input,.filters select {{ width:100%; margin:5px 0; padding:8px; border:1px solid var(--line); border-radius:6px; }}
    .article-group {{ border-bottom:1px solid var(--line); padding:10px 10px 12px; }}
    .article-title {{ font-weight:800; margin-bottom:6px; line-height:1.35; }}
    .nav-item {{ display:flex; gap:8px; align-items:center; justify-content:space-between; width:100%; border:1px solid transparent; background:#fff; padding:8px; border-radius:6px; text-align:left; cursor:pointer; color:var(--ink); }}
    .nav-item:hover,.nav-item.active {{ border-color:#93c5fd; background:#f0f7ff; }}
    .badge {{ display:inline-flex; align-items:center; border-radius:999px; padding:3px 8px; font-size:12px; font-weight:800; white-space:nowrap; background:#edf2f7; color:#334155; }}
    .status-approved_for_copy,.status-published_manual {{ background:#dcfce7; color:#166534; }}
    .status-revision_requested,.status-not_recommended {{ background:#fef3c7; color:#92400e; }}
    .status-rejected,.status-failed {{ background:#fee2e2; color:#991b1b; }}
    .panel {{ padding:18px; overflow:auto; }}
    .topline {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:14px 0; }}
    .field {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--soft); }}
    .field strong {{ display:block; font-size:12px; color:var(--muted); text-transform:uppercase; margin-bottom:5px; }}
    .draft-body {{ white-space:pre-wrap; line-height:1.55; border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .blogger-article-preview {{ line-height:1.6; border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
    .blogger-article-preview h2 {{ margin:20px 0 8px; font-size:22px; line-height:1.25; }}
    .blogger-article-preview h3 {{ margin:16px 0 8px; font-size:18px; line-height:1.3; }}
    .blogger-article-preview p {{ margin:0 0 14px; }}
    .blogger-article-preview ul,.blogger-article-preview ol {{ margin:0 0 16px 22px; padding:0; }}
    .callout {{ background:#ecfdf5; border-color:#99f6e4; color:#064e3b; }}
    .preview-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfdff; margin:12px 0; }}
    .preview-card img {{ max-width:100%; max-height:260px; border-radius:8px; border:1px solid var(--line); object-fit:cover; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }}
    button, a.button {{ padding:8px 11px; border:1px solid #c7d2e1; background:#fff; border-radius:7px; color:var(--ink); font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }}
    button.primary {{ background:#0f766e; border-color:#0f766e; color:#fff; }}
    button.danger {{ border-color:#fecaca; color:#991b1b; background:#fff5f5; }}
    textarea,input {{ width:100%; border:1px solid var(--line); border-radius:7px; padding:9px; font:inherit; }}
    textarea {{ min-height:220px; font-family:Arial, sans-serif; line-height:1.5; }}
    .edit {{ display:none; }}
    .editing .preview {{ display:none; }}
    .editing .edit {{ display:block; }}
    details {{ margin-top:14px; }}
    code {{ white-space:pre-wrap; overflow-wrap:anywhere; }}
    .notice {{ padding:10px; border-radius:7px; background:#ecfdf5; color:#065f46; margin:10px 0; display:none; }}
    .empty {{ padding:32px; }}
    @media(max-width:820px) {{ .layout {{ grid-template-columns:1fr; }} aside {{ max-height:none; }} .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Social Review Dashboard - {html.escape(resolved)}</h1>
      <div class="muted">Manual-only workflow. Review, edit, approve for copy, then use Menu E for manual publishing.</div>
    </div>
    <div class="header-actions">
      <button onclick="backToRunbot()">Back to Runbot Menu</button>
      <button class="danger" onclick="closeDashboardServer()">Close Dashboard Server</button>
    </div>
  </header>
  <main class="layout">
    <aside>
      <div class="filters">
        <input id="search" placeholder="Search article or platform">
        <select id="statusFilter">
          <option value="all">All</option>
          <option value="needs_social_review">Needs Review</option>
          <option value="approved_for_copy">Approved for Copy</option>
          <option value="pending_manual_publish">Pending Manual Publish</option>
          <option value="revision_requested">Revision Requested</option>
          <option value="rejected">Rejected</option>
          <option value="not_recommended">Not Recommended</option>
          <option value="published_manual">Published Manual</option>
        </select>
        <select id="platformFilter"><option value="all">All platforms</option></select>
        <select id="languageFilter"><option value="all">All languages</option><option value="en">English</option><option value="vi">Vietnamese</option></select>
      </div>
      <nav id="nav"></nav>
    </aside>
    <section class="panel" id="detail"><div class="empty">Select an article/platform draft from the left pane.</div></section>
  </main>
  <script id="dashboard-data" type="application/json">{html.escape(data_json, quote=False)}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
    const API = window.location.protocol === 'file:' ? null : '/api/social';
    let selected = null;
    const statusLabels = DATA.status_options || {{}};
    function h(v) {{ return String(v ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
    function allDrafts() {{ return DATA.items.flatMap(article => article.platforms.map(p => ({{...p, article_title: article.title, article_url: article.url}}))); }}
    function cleanPlatformOptions() {{
      const select = document.getElementById('platformFilter');
      [...new Set(allDrafts().map(p => p.platform))].sort().forEach(platform => {{
        const opt = document.createElement('option'); opt.value = platform; opt.textContent = allDrafts().find(p => p.platform === platform)?.platform_label || platform; select.appendChild(opt);
      }});
    }}
    function filteredDrafts(article) {{
      const q = document.getElementById('search').value.toLowerCase();
      const s = document.getElementById('statusFilter').value;
      const p = document.getElementById('platformFilter').value;
      const l = document.getElementById('languageFilter').value;
      return article.platforms.filter(d => {{
        const hay = `${{article.title}} ${{d.platform_label}} ${{d.title}} ${{d.body}}`.toLowerCase();
        return (!q || hay.includes(q)) && (s === 'all' || d.status === s) && (p === 'all' || d.platform === p) && (l === 'all' || d.language === l);
      }});
    }}
    function renderNav() {{
      const nav = document.getElementById('nav');
      nav.innerHTML = '';
      DATA.items.forEach(article => {{
        const drafts = filteredDrafts(article);
        if (!drafts.length) return;
        const group = document.createElement('div');
        group.className = 'article-group';
        group.innerHTML = `<div class="article-title">${{h(article.title)}}</div>`;
        drafts.forEach(d => {{
          const btn = document.createElement('button');
          btn.className = 'nav-item' + (selected && selected.slug === d.slug && selected.platform === d.platform ? ' active' : '');
          btn.innerHTML = `<span>${{h(d.platform_label)}}</span><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span>`;
          btn.onclick = () => {{ selected = d; renderNav(); renderDetail(d); }};
          group.appendChild(btn);
        }});
        nav.appendChild(group);
      }});
    }}
    function fallbackHashtags(d) {{
      const text = `${{d.article_title || ''}} ${{d.source_title || ''}} ${{d.body || ''}}`.toLowerCase();
      const tags = ['#AI'];
      if (text.includes('marketing')) tags.push('#MarketingAutomation');
      if (text.includes('automation')) tags.push('#Automation');
      if (text.includes('ifttt')) tags.push('#IFTTT');
      if (text.includes('saas') || text.includes('software')) tags.push('#SaaS');
      if (text.includes('workflow')) tags.push('#Workflow');
      if (text.includes('small business')) tags.push('#SmallBusiness');
      return [...new Set(tags)].slice(0, 5).join(' ');
    }}
    function tagsText(d) {{
      const raw = Array.isArray(d.hashtags) ? d.hashtags.join(' ') : String(d.hashtags || '');
      return raw.trim() || fallbackHashtags(d);
    }}
    function stripDraftHeading(text) {{
      return String(text || '').replace(/^#\\s+[^\\n]+\\n+/,'').trim();
    }}
    function cleanTitle(d) {{
      const title = String(d.title || '').trim();
      if (!title || /draft$/i.test(title) || / draft$/i.test(title) || /^quora answer draft$/i.test(title) || /^x draft$/i.test(title)) {{
        return String(d.source_title || d.article_title || '').trim();
      }}
      return title;
    }}
    function extractLine(text, prefix) {{
      const escaped = prefix.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
      const m = String(text || '').match(new RegExp('^' + escaped + '\\\\s*(.+)$', 'mi'));
      return m ? m[1].trim() : '';
    }}
    function appendIfMissing(text, value) {{
      const clean = String(value || '').trim();
      if (!clean || String(text || '').includes(clean)) return String(text || '').trim();
      return `${{String(text || '').trim()}}\\n\\n${{clean}}`.trim();
    }}
    function appendLinkBlock(text, label, url) {{
      const cleanUrl = String(url || '').trim();
      let cleanText = String(text || '').trim();
      if (!cleanUrl || cleanText.includes(cleanUrl)) return cleanText;
      return `${{cleanText}}\\n\\n${{label}}\\n${{cleanUrl}}`.trim();
    }}
    function escapeRegExp(value) {{
      return String(value || '').replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    }}
    function removeSourceUrlBlocks(text, url) {{
      const cleanUrl = String(url || '').trim();
      let body = String(text || '').trim();
      if (!cleanUrl) return body;
      const escaped = escapeRegExp(cleanUrl);
      [
        new RegExp('^This adapted draft[^\\n]*canonical[^\\n]*:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^The complete article[^\\n]*canonical[^\\n]*:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full source article:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full source article:\\\\s*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^I wrote a more detailed[^\\n]*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full guide here:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full guide here:\\\\s*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^' + escaped + '\\\\s*$', 'gmi')
      ].forEach(pattern => {{ body = body.replace(pattern, ''); }});
      return body.replace(/\\n{{3,}}/g, '\\n\\n').trim();
    }}
    function platformTags(d) {{
      return tagsText(d).replace(/#/g, '').split(/\\s+/).map(t => t.trim().toLowerCase()).filter(Boolean).slice(0, 4).join(', ');
    }}
    function imageWarning(d) {{
      const url = String(d.image_url || '').trim();
      const local = String(d.platform_image_path || d.local_image_path || '').trim();
      if (!url && !local) return 'No image is available for this draft.';
      if (/\\.svg($|\\?)/i.test(url)) return local ? `The website image is SVG, which some social platforms do not render. Use Copy Local Image File and upload this PNG manually: ${{local}}` : 'This image is SVG. Some social platforms do not render SVG previews; use Copy Image URL for manual upload or replace with a PNG/WebP social card.';
      return '';
    }}
    function assetUrl(d, download=false) {{
      const filename = d.platform_image_filename || 'og.png';
      if (!filename) return '';
      const url = `/assets/${{encodeURIComponent(d.batch_date)}}/${{encodeURIComponent(d.slug)}}/${{encodeURIComponent(filename)}}`;
      return download ? `${{url}}?download=1` : url;
    }}
    function cleanShortSocialBody(d) {{
      let body = stripDraftHeading(d.body)
        .replace(/^Title:\\s*/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      body = appendLinkBlock(body, 'Read the full article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\n${{tags}}`;
      return body.trim();
    }}
    function cleanPinterestText(d) {{
      const pinTitle = d.pin_title || cleanTitle(d);
      const description = d.pin_description || stripDraftHeading(d.body);
      const board = d.suggested_board || 'AI Tools Comparison';
      const keywords = Array.isArray(d.keywords) ? d.keywords.join('\\n') : String(d.keywords || '');
      const alt = d.alt_text || `Pinterest graphic for ${{pinTitle}}.`;
      return [
        'PIN TITLE',
        pinTitle,
        'PIN DESCRIPTION',
        description,
        'DESTINATION URL',
        d.destination_url || d.source_url,
        'SUGGESTED BOARD',
        board,
        'ALT TEXT',
        alt,
        'KEYWORDS',
        keywords
      ].filter(Boolean).join('\\n\\n');
    }}
    function pinterestField(d, field) {{
      if (field === 'pin_title') return d.pin_title || cleanTitle(d);
      if (field === 'pin_description') return d.pin_description || stripDraftHeading(d.body);
      if (field === 'destination_url') return d.destination_url || d.source_url;
      if (field === 'suggested_board') return d.suggested_board || 'AI Tools Comparison';
      if (field === 'keywords') return Array.isArray(d.keywords) ? d.keywords.join('\\n') : String(d.keywords || '');
      if (field === 'alt_text') return d.alt_text || `Pinterest graphic for ${{d.pin_title || cleanTitle(d)}}.`;
      if (field === 'image_path') return d.platform_image_path || d.local_image_path || '';
      return cleanPinterestText(d);
    }}
    function bloggerLabels(d) {{
      return Array.isArray(d.labels) ? d.labels.join(', ') : String(d.labels || tagsText(d));
    }}
    function cleanBloggerText(d) {{
      return String(d.plain_text_body || d.body || '')
        .replace(/^#\\s+.+$/m, '')
        .replace(/^Search description:\\s*.+$/gmi, '')
        .replace(/^Labels:\\s*.+$/gmi, '')
        .replace(/^Recommended permalink slug:\\s*.+$/gmi, '')
        .replace(/<a\\s+[^>]*>(.*?)<\\/a>/gi, '$1')
        .replace(/<\\/?[a-z][^>]*>/gi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
    }}
    function bloggerField(d, field) {{
      if (field === 'blogger_title') return d.blogger_title || d.title || '';
      if (field === 'search_description') return d.search_description || '';
      if (field === 'labels') return bloggerLabels(d);
      if (field === 'plain_text_body') return cleanBloggerText(d);
      if (field === 'html_body') return d.html_body || '';
      if (field === 'website_url') return d.source_article_url || d.source_url || '';
      if (field === 'permalink_slug') return d.recommended_permalink_slug || '';
      if (field === 'alt_text') return d.image_alt_text || '';
      if (field === 'image_path') return d.image_path || d.platform_image_path || d.local_image_path || '';
      return cleanBloggerText(d);
    }}
    function bloggerArticlePreviewHtml(d) {{
      const heading2 = new Set([
        'introduction',
        'why this comparison matters',
        'who should read this',
        'how to evaluate marketing automation software',
        'how to evaluate new ai tools by ifttt',
        'key buying checklist',
        'pricing considerations',
        'workflow examples',
        'pros',
        'cons',
        'alternatives',
        'common mistakes',
        'frequently asked questions',
        'final recommendation',
        'what to evaluate before choosing',
        'where the source article helps',
        'practical criteria for small teams',
        'who this is suitable for',
        'who should be cautious',
        'recommended decision workflow',
        'how to use the source guide',
        'common mistakes to avoid',
        'simple implementation notes',
        'conclusion',
        'disclosure'
      ]);
      const heading3 = new Set(['key takeaway', 'verification methods']);
      const blocks = cleanBloggerText(d).split(/\\n\\s*\\n/).map(x => x.trim()).filter(Boolean);
      return blocks.map(block => {{
        const lowered = block.toLowerCase();
        if (heading2.has(lowered)) return `<h2>${{h(block)}}</h2>`;
        if (heading3.has(lowered)) return `<div class="field callout"><strong>${{h(block)}}</strong></div>`;
        if (block.endsWith('?')) return `<h3>${{h(block)}}</h3>`;
        const lines = block.split('\\n').map(x => x.trim()).filter(Boolean);
        if (lines.length > 1 && lines.every(line => /^[-*]\\s+/.test(line))) {{
          return `<ul>${{lines.map(line => `<li>${{h(line.replace(/^[-*]\\s+/, ''))}}</li>`).join('')}}</ul>`;
        }}
        if (lines.length > 1 && lines.every(line => /^\\d+[.)]\\s+/.test(line))) {{
          return `<ol>${{lines.map(line => `<li>${{h(line.replace(/^\\d+[.)]\\s+/, ''))}}</li>`).join('')}}</ol>`;
        }}
        return `<p>${{h(block)}}</p>`;
      }}).join('');
    }}
    function blueskyField(d, field) {{
      const posts = Array.isArray(d.thread_posts) ? d.thread_posts : [];
      if (field === 'standalone_post') return d.standalone_post || d.body || '';
      if (field === 'full_thread') return posts.join('\\n\\n');
      if (field.startsWith('thread_post_')) {{
        const n = Number(field.replace('thread_post_', '')) - 1;
        return posts[n] || '';
      }}
      if (field === 'website_url') return d.article_url || d.source_url || '';
      if (field === 'alt_text') return d.image_alt_text || '';
      if (field === 'image_path') return d.image_path || d.platform_image_path || d.local_image_path || '';
      return [d.standalone_post || d.body || '', posts.join('\\n\\n')].filter(Boolean).join('\\n\\n');
    }}
    function cleanQuoraAnswer(d) {{
      let body = stripDraftHeading(d.body);
      const question = extractLine(body, 'Suggested Quora question:') || extractLine(body, 'Suggested question:') || d.title;
      body = body
        .replace(/^Suggested Quora question:\\s*.+$/gmi, '')
        .replace(/^Suggested question:\\s*.+$/gmi, '')
        .replace(/^Answer title\\/opening:\\s*/gmi, '')
        .replace(/^Full answer body:\\s*$/gmi, '')
        .replace(/^I wrote a more detailed.*$/gmi, '')
        .replace(/^Website source URL:\\s*.+$/gmi, '')
        .replace(/^Source link:\\s*.+$/gmi, '')
        .replace(/^Disclosure:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      body = removeSourceUrlBlocks(body, d.source_url);
      const disclosure = d.affiliate_disclosure
        ? `Disclosure: ${{d.affiliate_disclosure}}`
        : 'Disclosure: I am linking to an independent Smile AI Review Hub article.';
      const tags = tagsText(d);
      return [
        `Suggested question: ${{question}}`,
        body,
        'Read the full guide here:',
        d.source_url,
        disclosure,
        tags ? `Tags: ${{tags}}` : ''
      ].filter(Boolean).join('\\n\\n');
    }}
    function cleanLongFormBody(d) {{
      return stripDraftHeading(d.body)
        .replace(/^Canonical URL instruction.*$/gmi, '')
        .replace(/^Read the original review:\\s*.+$/gmi, '')
        .replace(/^Full original guide:\\s*.+$/gmi, '')
        .replace(/^Full review:\\s*.+$/gmi, '')
        .replace(/^Canonical URL note:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
    }}
    function cleanDevToBody(d) {{
      let body = removeSourceUrlBlocks(cleanLongFormBody(d), d.source_url);
      body = appendLinkBlock(body, 'Read the full source article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\n${{tags}}`;
      return body.trim();
    }}
    function cleanLongFormPostBody(d) {{
      let body = removeSourceUrlBlocks(cleanLongFormBody(d), d.source_url);
      body = appendLinkBlock(body, 'Read the full source article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\nTags: ${{tags}}`;
      if (d.affiliate_disclosure && !body.includes(d.affiliate_disclosure)) body = `${{body}}\\n\\nDisclosure: ${{d.affiliate_disclosure}}`;
      return body.trim();
    }}
    function cleanDevToDraft(d) {{
      const tags = platformTags(d);
      const frontMatter = [
        '---',
        `title: "${{cleanTitle(d).replace(/"/g, '\\\\"')}}"`,
        'published: false',
        d.canonical_url ? `canonical_url: ${{d.canonical_url}}` : '',
        d.image_url && !/\\.svg($|\\?)/i.test(d.image_url) ? `cover_image: ${{d.image_url}}` : '',
        tags ? `tags: ${{tags}}` : '',
        '---'
      ].filter(Boolean).join('\\n');
      const body = cleanDevToBody(d);
      const note = imageWarning(d);
      return [
        frontMatter,
        body,
        d.affiliate_disclosure ? `Disclosure: ${{d.affiliate_disclosure}}` : ''
      ].filter(Boolean).join('\\n\\n');
    }}
    function cleanProductHuntText(d) {{
      let body = stripDraftHeading(d.body)
        .replace(/^Discussion title:\\s*/gmi, '')
        .replace(/^Concise introduction:\\s*/gmi, '')
        .replace(/^Website source URL:\\s*.+$/gmi, '')
        .replace(/^Disclosure:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      return [
        cleanTitle(d),
        body,
        'Read more:',
        d.source_url,
        d.affiliate_disclosure ? `Disclosure: ${{d.affiliate_disclosure}}` : '',
        tagsText(d)
      ].filter(Boolean).join('\\n\\n');
    }}
    function copyAllText(d) {{
      const tags = tagsText(d);
      if (d.platform === 'pinterest') return cleanPinterestText(d);
      if (d.platform === 'blogger') return bloggerField(d, 'all');
      if (d.platform === 'bluesky') return blueskyField(d, 'all');
      if (d.platform === 'quora') return cleanQuoraAnswer(d);
      if (d.platform === 'producthunt') return cleanProductHuntText(d);
      if (d.platform === 'devto') return cleanDevToDraft(d);
      if (['medium','hashnode','blogger'].includes(d.platform)) return [`Title: ${{cleanTitle(d)}}`, cleanLongFormPostBody(d)].filter(Boolean).join('\\n\\n');
      return cleanShortSocialBody(d);
    }}
    function pinterestPanel(d) {{
      if (d.platform !== 'pinterest') return '';
      const keywords = Array.isArray(d.keywords) ? d.keywords.join(', ') : String(d.keywords || '');
      const published = d.final_published_url || '';
      const publishedActions = published
        ? `<button onclick="window.open('${{h(published)}}', '_blank', 'noopener,noreferrer')">Open Published Pin</button><button onclick="copyPublishedPinUrl()">Copy Published Pin URL</button><button class="danger" onclick="resetPinterestPublished()">Reset Published Status</button>`
        : `<button disabled>Open Published Pin</button><button disabled>Copy Published Pin URL</button>`;
      return `
        <div class="field"><strong>Pinterest manual checklist</strong>
          <ol>
            <li>Upload pinterest.png</li>
            <li>Paste Pin Title</li>
            <li>Paste Pin Description</li>
            <li>Paste Destination URL</li>
            <li>Select Suggested Board</li>
            <li>Add Alt Text if available</li>
            <li>Publish manually</li>
            <li>Paste the final Pinterest Pin URL below</li>
          </ol>
        </div>
        <div class="grid">
          <div class="field"><strong>Pin Title</strong>${{h(d.pin_title || cleanTitle(d))}}</div>
          <div class="field"><strong>Destination URL</strong>${{h(d.destination_url || d.source_url)}}</div>
          <div class="field"><strong>Suggested Board</strong>${{h(d.suggested_board || 'AI Tools Comparison')}}</div>
          <div class="field"><strong>Keywords</strong>${{h(keywords)}}</div>
          <div class="field"><strong>Alt Text</strong>${{h(d.alt_text || '')}}</div>
          <div class="field"><strong>Overlay Text</strong>${{h(d.overlay_text || '')}}</div>
        </div>
        <div class="field"><strong>Pin Description Only</strong><div class="draft-body">${{h(d.pin_description || d.body || '')}}</div></div>
        <div class="field">
          <strong>Post-publication</strong>
          <div class="grid">
            <div><strong>Published status</strong><br><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span></div>
            <div><strong>Published at</strong><br>${{h(d.published_at || '-')}}</div>
            <div><strong>Validation</strong><br>${{h(d.final_url_validation_message || '-')}}</div>
            <div><strong>Published URL</strong><br>${{published ? `<a href="${{h(published)}}" target="_blank" rel="noopener noreferrer">${{h(published)}}</a>` : '-'}}</div>
          </div>
          <label>Final Pinterest URL<input id="finalPinterestUrl" value="${{h(published)}}" placeholder="https://www.pinterest.com/pin/1098526534136812938/"></label>
          <div class="actions"><button class="primary" onclick="savePinterestUrl()">Save Pinterest URL</button><button onclick="markPinterestPending()">Mark Pending</button>${{publishedActions}}</div>
        </div>
      `;
    }}
    function bloggerPanel(d) {{
      if (d.platform !== 'blogger') return '';
      return `
        <div class="topline"><h2>${{h(d.blogger_title || d.title || '')}}</h2><span class="badge">${{h(d.platform_label)}}</span><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span></div>
        <div class="grid">
          <div class="field"><strong>SEO score</strong>${{h(d.seo_score || 0)}}/100</div>
          <div class="field"><strong>Estimated reading time</strong>${{h(d.estimated_reading_time_minutes || 0)}} min</div>
          <div class="field"><strong>Search description</strong>${{h(d.search_description || '')}}</div>
          <div class="field"><strong>Labels</strong>${{h(bloggerLabels(d))}}</div>
          <div class="field"><strong>Recommended permalink slug</strong>${{h(d.recommended_permalink_slug || '')}}</div>
          <div class="field"><strong>Word count</strong>${{h(d.blogger_word_count || 0)}}</div>
          <div class="field"><strong>Heading count</strong>${{h(d.heading_count || 0)}}</div>
          <div class="field"><strong>FAQ count</strong>${{h(d.faq_count || 0)}}</div>
          <div class="field"><strong>Internal links</strong>${{h(d.internal_link_count || 0)}}</div>
          <div class="field"><strong>External links</strong>${{h(d.external_link_count || 0)}}</div>
          <div class="field"><strong>JSON-LD status</strong>${{h(d.json_ld_status || 'missing')}}</div>
          <div class="field"><strong>Source website URL</strong>${{h(d.source_article_url || d.source_url || '')}}</div>
          <div class="field"><strong>Alt text</strong>${{h(d.image_alt_text || '')}}</div>
          <div class="field"><strong>Image caption</strong>${{h(d.image_caption || '')}}</div>
          <div class="field"><strong>Recommended image filename</strong>${{h(d.recommended_image_filename || '')}}</div>
          <div class="field"><strong>OpenGraph title</strong>${{h(d.open_graph_title || '')}}</div>
          <div class="field"><strong>OpenGraph description</strong>${{h(d.open_graph_description || '')}}</div>
          <div class="field"><strong>Twitter card description</strong>${{h(d.twitter_card_description || '')}}</div>
        </div>
        <div class="field"><strong>Article preview</strong><div class="blogger-article-preview">${{bloggerArticlePreviewHtml(d)}}</div></div>
        <details class="field"><summary><strong>HTML preview</strong></summary><textarea readonly>${{h(d.html_body || '')}}</textarea></details>
        <div class="field"><strong>Publishing assets</strong><div>Image file: <code>${{h(d.image_path || d.platform_image_path || d.local_image_path || '')}}</code></div></div>
        <div class="field"><strong>Disclosure</strong>${{h(d.disclosure || '')}}</div>
      `;
    }}
    function blueskyPanel(d) {{
      if (d.platform !== 'bluesky') return '';
      const posts = Array.isArray(d.thread_posts) ? d.thread_posts : [];
      const counts = d.character_counts || {{}};
      const postHtml = posts.map((post, index) => `<div class="field"><strong>Thread post ${{index + 1}} (${{post.length}}/${{d.bluesky_character_limit || 300}})</strong><div class="draft-body">${{h(post)}}</div></div>`).join('');
      return `
        <div class="field"><strong>Standalone post (${{h((d.standalone_post || d.body || '').length)}}/${{h(d.bluesky_character_limit || 300)}})</strong><div class="draft-body">${{h(d.standalone_post || d.body || '')}}</div></div>
        <div class="field"><strong>Thread version</strong>${{postHtml}}</div>
        <div class="grid">
          <div class="field"><strong>Website URL</strong>${{h(d.article_url || d.source_url || '')}}</div>
          <div class="field"><strong>Hashtags</strong>${{h(tagsText(d))}}</div>
          <div class="field"><strong>Alt text</strong>${{h(d.image_alt_text || '')}}</div>
          <div class="field"><strong>Character counts</strong>${{h(JSON.stringify(counts))}}</div>
        </div>
      `;
    }}
    function actionButtons(d) {{
      if (d.platform === 'pinterest') {{
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download PNG</a><button onclick="copyField('pin_title')">Copy Pin Title</button><button onclick="copyField('pin_description')">Copy Pin Description</button><button onclick="copyField('destination_url')">Copy Destination URL</button><button onclick="copyField('suggested_board')">Copy Suggested Board</button><button onclick="copyField('keywords')">Copy Keywords</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button onclick="copyField('image_path')">Copy Image Path</button><button class="primary" onclick="copyField('all')">Copy All Fields</button>`;
      }}
      if (d.platform === 'blogger') {{
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('blogger_title')">Copy Blogger Title</button><button onclick="copyField('search_description')">Copy Search Description</button><button onclick="copyField('labels')">Copy Labels</button><button onclick="copyField('plain_text_body')">Copy Plain Text Body</button><button title="Paste only in Blogger HTML view" onclick="copyField('html_body')">Copy HTML (HTML mode only)</button><button onclick="copyField('website_url')">Copy Website URL</button><button onclick="copyField('permalink_slug')">Copy Permalink Slug</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button class="primary" onclick="copyField('all')">Copy Compose Body</button>`;
      }}
      if (d.platform === 'bluesky') {{
        const threadButtons = (Array.isArray(d.thread_posts) ? d.thread_posts : []).map((_, index) => `<button onclick="copyField('thread_post_${{index + 1}}')">Copy Thread Post ${{index + 1}}</button>`).join('');
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('standalone_post')">Copy Standalone Post</button><button onclick="copyField('full_thread')">Copy Full Thread</button>${{threadButtons}}<button onclick="copyField('website_url')">Copy Website URL</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button class="primary" onclick="copyField('all')">Copy Bluesky Package</button>`;
      }}
      const urlLabel = d.content_lane === 'SOCIAL_HOT_UNCONFIRMED' ? 'Copy Source URL' : 'Copy Website URL';
      return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('title')">Copy Title</button><button onclick="copyField('body')">Copy Body</button><button onclick="copyField('cta')">Copy CTA</button><button onclick="copyField('hashtags')">Copy Hashtags</button><button onclick="copyField('url')">${{urlLabel}}</button><button onclick="copyField('image')">Copy Image URL</button><button onclick="copyField('local_image')">Copy Image Path</button><button class="primary" onclick="copyField('all')">Copy All</button>`;
    }}
    function variantComparison(d) {{
      const variants = Array.isArray(d.variants) ? d.variants : [];
      if (!variants.length) return '';
      return `<div class="field"><strong>CONTENT COMPONENTS (read-only review aids)</strong><div class="grid">${{variants.map(v => {{
        const count = v.platform_limit ? `${{v.character_count}} / ${{v.platform_limit}}` : String(v.character_count);
        const invalid = v.platform_validation_status === 'INVALID_PLATFORM_LIMIT';
        return `<div class="field">
          <div class="topline"><strong>Component ${{h(v.label)}} · ${{h(v.variant_strategy)}}</strong></div>
          <div><strong>Today's angle:</strong> ${{h(d.today_social_angle || v.social_angle)}}</div>
          <div><strong>Characters:</strong> ${{h(count)}} · <strong>${{invalid ? 'INVALID_PLATFORM_LIMIT' : 'PASS'}}</strong></div>
          <div><strong>Evidence:</strong> ${{h((v.evidence_refs || []).length ? 'INHERITED' : d.evidence_status)}}</div>
          <div><strong>New claims:</strong> ${{h((v.new_claims || []).length ? 'EVIDENCE_REQUIRED' : 'PASS')}}</div>
          <div class="draft-body">${{h(v.text)}}</div>
        </div>`;
      }}).join('')}}</div></div>`;
    }}
    function renderDetail(d) {{
      document.getElementById('detail').className = 'panel';
      const over = ['x','twitter'].includes(d.platform) && d.character_count > 280 ? '<div class="field"><strong>Warning</strong>X draft is over 280 characters.</div>' : '';
      const imageSrc = assetUrl(d) || d.image_url;
      const img = imageSrc ? `<img src="${{h(imageSrc)}}" alt="" style="object-fit:contain;max-height:360px;width:100%;background:#f8fafc">` : '<span class="muted">No image available</span>';
      const warnings = (d.validation_warnings || []).map(w => `<li>${{h(w)}}</li>`).join('');
      const q = d.social_value_validation || {{}};
      const passWarn = value => value ? 'PASS' : 'WARN';
      const qualityDiagnostics = Object.keys(q).length ? `<div class="field"><strong>Social quality</strong>
        What happened: ${{passWarn(q.what_happened_present)}}<br>
        Why it matters: ${{passWarn(q.why_it_matters_present)}}<br>
        Practical takeaway: ${{passWarn(q.practical_takeaway_present)}}<br>
        Source rendering: ${{q.official_source_present ? 'PASS' : 'BLOCK'}}<br>
        Future promise: ${{q.unsupported_future_promise ? 'BLOCK' : 'PASS'}}<br>
        Generic-content risk: ${{h(q.generic_content_risk || 'LOW')}}<br>
        Value score: ${{h(q.value_score)}} / 100</div>` : '';
      const approveButton = d.approval_blocked
        ? `<button class="primary" disabled title="${{h((d.approval_block_reasons || []).join(', '))}}">Approval Blocked</button>`
        : `<button class="primary" onclick="setStatus('approved_for_copy', true)">Approve Final</button>`;
      const genericHeader = d.platform === 'blogger' ? '' : `<div class="topline"><h2>${{h(d.article_title)}}</h2><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span><span class="badge">${{h(d.platform_label)}}</span></div>`;
      const genericMetaGrid = d.platform === 'blogger' ? '' : `<div class="grid">
            <div class="field"><strong>Language</strong>${{h(d.language)}}</div>
            <div class="field"><strong>Character count</strong>${{h(d.character_count)}}</div>
            <div class="field"><strong>Official source</strong>${{h(d.official_source_name || 'Missing')}}<br><a href="${{h(d.official_source_url)}}" target="_blank">${{h(d.official_source_url)}}</a><br>Status: ${{h(d.source_status)}}</div>
            <div class="field"><strong>Canonical URL</strong><a href="${{h(d.canonical_url)}}" target="_blank">${{h(d.canonical_url)}}</a></div>
            <div class="field"><strong>Image asset</strong>${{h(d.platform_image_filename || '-')}} - ${{h(d.platform_image_width)}}x${{h(d.platform_image_height)}} - ${{h(d.platform_image_size)}} bytes - ${{h(d.asset_validation_status)}}</div>
          </div>`;
      const genericPreviewBody = d.platform === 'pinterest' ? (d.pin_description || d.body) : copyAllText(d);
      const genericPreview = d.platform === 'blogger' ? '' : `<div class="preview-card platform-${{h(d.platform)}}">${{img}}<h3>${{h(cleanTitle(d))}}</h3><div class="draft-body">${{h(genericPreviewBody)}}</div><p><strong>CTA:</strong> ${{h(d.cta)}}</p><p><strong>Hashtags/tags:</strong> ${{h(tagsText(d))}}</p>${{imageWarning(d) ? `<p class="notice" style="display:block"><strong>Image:</strong> ${{h(imageWarning(d))}}</p>` : ''}}</div>`;
      const bloggerImagePreview = d.platform === 'blogger' ? `<div class="preview-card platform-blogger">${{img}}${{imageWarning(d) ? `<p class="notice" style="display:block"><strong>Image:</strong> ${{h(imageWarning(d))}}</p>` : ''}}</div>` : '';
      document.getElementById('detail').innerHTML = `
        <div class="preview">
          ${{genericHeader}}
          <div id="notice" class="notice"></div>
          <div class="grid" style="${{d.platform === 'blogger' ? 'display:none' : ''}}">
            <div class="field"><strong>Language</strong>${{h(d.language)}}</div>
            <div class="field"><strong>Character count</strong>${{h(d.character_count)}}</div>
            <div class="field"><strong>Source website URL</strong><a href="${{h(d.source_url)}}" target="_blank">${{h(d.source_url)}}</a></div>
            <div class="field"><strong>Canonical URL</strong><a href="${{h(d.canonical_url)}}" target="_blank">${{h(d.canonical_url)}}</a></div>
            <div class="field"><strong>Image asset</strong>${{h(d.platform_image_filename || '-')}} · ${{h(d.platform_image_width)}}x${{h(d.platform_image_height)}} · ${{h(d.platform_image_size)}} bytes · ${{h(d.asset_validation_status)}}</div>
          </div>
          ${{bloggerImagePreview}}
          ${{variantComparison(d)}}
          <div class="field"><strong>FINAL ${{h(d.platform_label).toUpperCase()}} POST</strong><div class="draft-body">${{h(d.body || '')}}</div></div>
          ${{genericPreview}}
          ${{pinterestPanel(d)}}
          ${{bloggerPanel(d)}}
          ${{blueskyPanel(d)}}
          ${{over}}
          <div class="field"><strong>Validation warnings</strong>${{warnings ? `<ul>${{warnings}}</ul>` : 'None'}}</div>
          <div class="grid">
            <div class="field"><strong>Website Root</strong>${{h(d.root_title || d.root_topic_id || '-')}}</div>
            <div class="field"><strong>Source Article</strong>${{h(d.source_article_slug || d.slug)}}</div>
            <div class="field"><strong>Today's Social Angle</strong>${{h(d.today_social_angle || d.social_angle || '-')}}</div>
            <div class="field"><strong>Content Model</strong>${{h(d.content_model || '-')}}</div>
            <div class="field"><strong>Evidence Status</strong>${{h(d.evidence_status)}}</div>
            <div class="field"><strong>New Claim Status</strong>${{h(d.new_claim_status)}}</div>
            <div class="field"><strong>Visual Recommendation</strong>${{h(d.visual_recommended ? d.visual_type : 'NO_VISUAL')}}<br>${{h(d.visual_concept || '')}}</div>
          </div>
          ${{qualityDiagnostics}}
          <div class="field"><strong>Reviewer notes</strong><div class="draft-body">${{h(d.reviewer_notes || '')}}</div></div>
          <div class="actions">
            ${{actionButtons(d)}}
          </div>
          <div class="actions">
            <button onclick="startEdit()">Edit Final</button><button onclick="regenerateFinal()">Regenerate Final</button>${{approveButton}}<button class="danger" onclick="setStatus('rejected', true)">Reject Final</button><button onclick="setStatus('revision_requested', false)">Request Revision</button><button onclick="setStatus('not_recommended', true)">Mark Not Recommended</button><button onclick="setStatus('needs_social_review', false)">Reset to Needs Review</button>
          </div>
          <details><summary>Technical details</summary><p><strong>Created:</strong> ${{h(d.created_at) || '-'}}</p><p><strong>Updated:</strong> ${{h(d.updated_at) || '-'}}</p><p><strong>Draft:</strong> <code>${{h(d.draft_path)}}</code></p><p><strong>Metadata:</strong> <code>${{h(d.metadata_path)}}</code></p></details>
        </div>
        <div class="edit">
          <h2>Edit ${{h(d.platform_label)}} Draft</h2>
          <label>Title<input id="editTitle" value="${{h(d.title)}}"></label>
          <label>Body<textarea id="editBody">${{h(d.body)}}</textarea></label>
          <label>CTA<input id="editCta" value="${{h(d.cta)}}"></label>
          <label>Hashtags/tags<input id="editTags" value="${{h(tagsText(d))}}"></label>
          <label>Image URL<input id="editImage" value="${{h(d.image_url)}}"></label>
          <label>Reviewer notes<textarea id="editNotes">${{h(d.reviewer_notes || '')}}</textarea></label>
          <div class="actions"><button class="primary" onclick="saveEdit()">Save Changes</button><button onclick="cancelEdit()">Cancel Edit</button></div>
        </div>`;
    }}
    function selectedKey() {{ return {{date: DATA.batch_date, slug: selected.slug, platform: selected.platform}}; }}
    function show(msg) {{ const n = document.getElementById('notice'); if (n) {{ n.textContent = msg; n.style.display = 'block'; }} }}
    async function post(action, payload) {{
      if (!API) throw new Error('Open this dashboard through Menu G local server for write/copy actions.');
      const res = await fetch(`${{API}}/${{action}}`, {{method:'POST', headers:{{'Content-Type':'application/json; charset=utf-8'}}, body:JSON.stringify(payload)}});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Request failed');
      return data;
    }}
    function backToRunbot() {{
      alert('Return to the already-running Runbot Menu window. Browsers cannot safely control the original CMD process.');
      try {{ window.close(); }} catch(e) {{}}
    }}
    async function closeDashboardServer() {{
      if (!confirm('Close only the local Social Review Dashboard server?')) return;
      try {{
        const data = await post('stop', {{date: DATA.batch_date, slug: selected?.slug || 'dashboard', platform: selected?.platform || 'dashboard'}});
        document.body.innerHTML = `<main class="panel" style="margin:32px"><h1>Dashboard server stopped</h1><p>${{h(data.message || 'Dashboard server stopped. You may close this browser tab and continue in Runbot Menu.')}}</p></main>`;
      }} catch(e) {{ alert(e.message); }}
    }}
    async function copyField(field) {{
      try {{
        let text = '';
        if (selected.platform === 'pinterest' && ['pin_title','pin_description','destination_url','suggested_board','keywords','alt_text','image_path'].includes(field)) text = pinterestField(selected, field);
        else if (selected.platform === 'pinterest' && field === 'body') text = pinterestField(selected, 'pin_description');
        else if (selected.platform === 'blogger' && ['blogger_title','search_description','labels','plain_text_body','html_body','website_url','permalink_slug','alt_text','image_path','all'].includes(field)) text = bloggerField(selected, field);
        else if (selected.platform === 'bluesky' && (['standalone_post','full_thread','website_url','alt_text','image_path','all'].includes(field) || field.startsWith('thread_post_'))) text = blueskyField(selected, field);
        else if (selected.platform === 'devto' && field === 'body') text = cleanDevToBody(selected);
        else if (['medium','hashnode'].includes(selected.platform) && field === 'body') text = cleanLongFormPostBody(selected);
        else if (selected.platform === 'producthunt' && field === 'body') text = cleanProductHuntText(selected);
        else if (field === 'title') text = selected.title;
        else if (field === 'body') text = selected.body;
        else if (field === 'cta') text = selected.cta;
        else if (field === 'hashtags') text = tagsText(selected);
        else if (field === 'url') text = selected.source_url;
        else if (field === 'image') text = selected.image_url && !/\\.svg($|\\?)/i.test(selected.image_url) ? selected.image_url : '';
        else if (field === 'local_image') text = selected.platform_image_path || selected.local_image_path || selected.image_url;
        else text = copyAllText(selected);
        try {{ await navigator.clipboard.writeText(text); show('Copied successfully'); }}
        catch (e) {{ const data = await post('copy', {{...selectedKey(), field, text}}); show(`Clipboard unavailable. UTF-8 file created at: ${{data.file_path}}`); }}
      }} catch (e) {{ alert(e.message); }}
    }}
    function startEdit() {{ document.getElementById('detail').classList.add('editing'); }}
    function cancelEdit() {{ document.getElementById('detail').classList.remove('editing'); }}
    async function saveEdit() {{
      try {{
        const data = await post('save', {{...selectedKey(), title:editTitle.value, body:editBody.value, cta:editCta.value, hashtags:editTags.value, image_url:editImage.value, reviewer_notes:editNotes.value}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Saved changes');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function setStatus(status, confirmFirst) {{
      if (confirmFirst && !confirm(`Change status to ${{statusLabels[status] || status}}?`)) return;
      try {{
        const notes = selected.reviewer_notes || '';
        const data = await post('status', {{...selectedKey(), status, reviewer_notes: notes}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Status updated');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function chooseVariant(variant, approve) {{
      if (approve && !confirm(`Approve variant ${{variant.replace('.md','')}} for copy?`)) return;
      try {{
        const data = await post('select-variant', {{...selectedKey(), variant, approve, reviewer_notes:selected.reviewer_notes || ''}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show(approve ? `Approved ${{variant}}` : `Selected ${{variant}}`);
      }} catch(e) {{ alert(e.message); }}
    }}
    async function regenerateFinal() {{
      if (!confirm('Recompose the final platform post from components A/B/C?')) return;
      try {{
        const data = await post('regenerate-final', {{...selectedKey(), reviewer_notes:selected.reviewer_notes || ''}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Final post recomposed from A/B/C.');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function markPinterestPending() {{
      if (!selected || selected.platform !== 'pinterest') return;
      try {{
        const data = await post('pinterest-pending', selectedKey());
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest draft marked Pending Manual Publish');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function savePinterestUrl() {{
      if (!selected || selected.platform !== 'pinterest') return;
      const input = document.getElementById('finalPinterestUrl');
      const url = (input?.value || '').trim();
      if (!url) {{ alert('Final Pinterest URL is required.'); return; }}
      if (!confirm('Confirm that this Pin has been published manually?')) return;
      try {{
        const data = await post('pinterest-published-url', {{...selectedKey(), final_published_url: url}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest URL saved. Status is Published Manual.');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function copyPublishedPinUrl() {{
      if (!selected?.final_published_url) return;
      try {{
        await navigator.clipboard.writeText(selected.final_published_url);
        show('Published Pin URL copied');
      }} catch(e) {{
        const data = await post('copy', {{...selectedKey(), field:'final_published_url', text:selected.final_published_url}});
        show(`Clipboard unavailable. UTF-8 file created at: ${{data.file_path}}`);
      }}
    }}
    async function resetPinterestPublished() {{
      if (!selected || selected.platform !== 'pinterest') return;
      if (!confirm('Reset Published Manual status and clear the saved Pin URL?')) return;
      try {{
        const data = await post('pinterest-reset-published', {{...selectedKey(), confirmed:true}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest published status reset');
      }} catch(e) {{ alert(e.message); }}
    }}
    ['search','statusFilter','platformFilter','languageFilter'].forEach(id => document.addEventListener('input', e => {{ if (e.target.id === id) renderNav(); }}));
    cleanPlatformOptions(); renderNav(); const first = allDrafts()[0]; if (first) {{ selected = first; renderNav(); renderDetail(first); }}
  </script>
</body>
</html>
"""
