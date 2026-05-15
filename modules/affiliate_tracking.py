from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import pandas as pd

from config import settings
from modules.affiliate_links import load_affiliate_links, save_affiliate_links, slugify, to_bool


CLICK_EVENT_COLUMNS = [
    "timestamp",
    "session_id",
    "click_id",
    "tool_slug",
    "tool_name",
    "source_page",
    "source_page_type",
    "cta_label",
    "target_url",
    "referrer",
    "event_type",
    "page_load_seconds",
    "user_agent_hint",
    "is_suspicious",
    "suspicious_reason",
    "click_quality_score",
]

REQUIRED_AFFILIATE_COLUMNS = [
    "tool_slug",
    "tool_name",
    "official_url",
    "affiliate_url",
    "affiliate_status",
    "notes",
]

AFFILIATE_TRACKING_REPORT_COLUMNS = [
    "tracking_id",
    "source",
    "medium",
    "campaign",
    "content",
    "platform",
    "target_url",
    "tracked_url",
    "page_slug",
    "topic",
    "tool_name",
    "status",
    "recommendation",
]

REDIRECT_MAP_COLUMNS = [
    "tracking_id",
    "source",
    "medium",
    "campaign",
    "content",
    "platform",
    "target_url",
    "tracked_url",
    "redirect_path",
    "status",
]


def click_events_file() -> Path:
    return settings.data_dir / "click_events.csv"


def ensure_click_events() -> pd.DataFrame:
    path = click_events_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            df = pd.read_csv(path).fillna("")
        except Exception:
            df = pd.DataFrame(columns=CLICK_EVENT_COLUMNS)
    else:
        df = pd.DataFrame(columns=CLICK_EVENT_COLUMNS)
    for column in CLICK_EVENT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[CLICK_EVENT_COLUMNS]
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def load_click_events() -> pd.DataFrame:
    return ensure_click_events()


def append_click_event(event: dict[str, str]) -> pd.DataFrame:
    df = ensure_click_events()
    row = {column: str(event.get(column, "")).strip() for column in CLICK_EVENT_COLUMNS}
    row["timestamp"] = row["timestamp"] or datetime.now(timezone.utc).isoformat()
    row = enrich_click_quality(row, df)
    updated = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    updated.to_csv(click_events_file(), index=False)
    return updated


def enrich_click_quality(event: dict[str, str], history: pd.DataFrame | None = None) -> dict[str, str]:
    """Classify click quality without storing personal data."""
    row = {column: str(event.get(column, "")).strip() for column in CLICK_EVENT_COLUMNS}
    reasons: list[str] = []
    score = 100
    session_id = row.get("session_id", "")
    tool_slug = row.get("tool_slug", "")
    source_page = row.get("source_page", "")
    referrer = row.get("referrer", "")
    user_agent = row.get("user_agent_hint", "")
    click_time = pd.to_datetime(row.get("timestamp"), utc=True, errors="coerce")

    page_load_seconds = _to_float(row.get("page_load_seconds"))
    if page_load_seconds is not None and page_load_seconds < 2:
        reasons.append("page_load_under_2_seconds")
        score -= 30

    if not source_page or not referrer:
        reasons.append("missing_source_or_referrer")
        score -= 15

    if _looks_unusual_user_agent(user_agent):
        reasons.append("unusual_user_agent")
        score -= 20

    if history is not None and not history.empty and session_id and pd.notna(click_time):
        history = history.copy()
        if "timestamp" in history.columns:
            history["_parsed_time"] = pd.to_datetime(history["timestamp"], utc=True, errors="coerce")
            recent = history[
                (history.get("session_id", "").astype(str) == session_id)
                & (history["_parsed_time"] >= click_time - timedelta(minutes=5))
                & (history["_parsed_time"] <= click_time)
            ]
            if tool_slug and "tool_slug" in recent.columns:
                same_tool_count = int((recent["tool_slug"].astype(str) == tool_slug).sum())
                if same_tool_count >= 3:
                    reasons.append("same_tool_more_than_3_clicks_in_5_minutes")
                    score -= 35
            if "tool_slug" in recent.columns and len(recent) >= 4 and recent["tool_slug"].astype(str).nunique() >= 4:
                reasons.append("many_tools_clicked_quickly")
                score -= 25

    score = max(0, min(100, score))
    row["click_quality_score"] = str(score)
    row["is_suspicious"] = "true" if score < 60 or reasons else "false"
    row["suspicious_reason"] = "; ".join(dict.fromkeys(reasons))
    return row


def _to_float(value: str) -> float | None:
    try:
        if value in {"", "None", "nan"}:
            return None
        return float(value)
    except Exception:
        return None


def _looks_unusual_user_agent(value: str) -> bool:
    user_agent = str(value or "").strip().lower()
    if len(user_agent) < 4:
        return True
    suspicious_markers = ["curl", "wget", "python-requests", "scrapy", "spider", "crawler", "headless"]
    return any(marker in user_agent for marker in suspicious_markers)


def tracking_url(tool_slug: str, source_page: str = "", cta_label: str = "official_site") -> str:
    slug = slugify(tool_slug)
    query = []
    if source_page:
        query.append(f"src={quote(source_page)}")
    if cta_label:
        query.append(f"cta={quote(cta_label)}")
    suffix = "?" + "&".join(query) if query else ""
    return f"/go/{slug}/{suffix}"


def generate_go_pages(output: Path, affiliate_links: pd.DataFrame | None = None) -> int:
    ensure_click_events()
    links = affiliate_links if affiliate_links is not None and not affiliate_links.empty else load_affiliate_links()
    links = save_affiliate_links(links)
    go_root = output / "go"
    go_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for _, row in links.iterrows():
        slug = str(row.get("tool_slug") or row.get("slug") or slugify(row.get("tool_name") or row.get("brand"))).strip()
        name = str(row.get("tool_name") or row.get("brand") or slug.replace("-", " ").title()).strip()
        if not slug:
            continue
        target_url, event_type, note = resolve_target(row)
        folder = go_root / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(go_page_html(slug, name, target_url, event_type, note), encoding="utf-8")
        count += 1
    return count


def rewrite_outbound_ctas(output: Path, affiliate_links: pd.DataFrame | None = None) -> int:
    links = affiliate_links if affiliate_links is not None and not affiliate_links.empty else load_affiliate_links()
    links = save_affiliate_links(links)
    replacements = []
    for _, row in links.iterrows():
        slug = str(row.get("tool_slug") or row.get("slug") or "").strip()
        if not slug:
            continue
        for column, cta in [("affiliate_url", "affiliate_link"), ("official_url", "official_site")]:
            url = str(row.get(column, "")).strip()
            if url:
                replacements.append((url, slug, cta))
    changed = 0
    for file in output.rglob("*.html"):
        rel = file.relative_to(output).as_posix()
        if rel.startswith("go/"):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        original = text
        source_page = "/" if rel == "index.html" else "/" + rel.removesuffix("index.html")
        for url, slug, cta in replacements:
            tracked = tracking_url(slug, source_page, cta)
            text = replace_href(text, url, tracked)
            text = replace_href(text, html.escape(url, quote=True), tracked)
        if "/go/" in text:
            text = inject_click_timer_script(text)
        if text != original:
            file.write_text(text, encoding="utf-8")
            changed += 1
    return changed


def replace_href(text: str, old_url: str, new_url: str) -> str:
    if not old_url:
        return text
    pattern = re.compile(rf"href=(['\"]){re.escape(old_url)}\1")
    return pattern.sub(lambda match: f"href={match.group(1)}{html.escape(new_url, quote=True)}{match.group(1)}", text)


def inject_click_timer_script(text: str) -> str:
    marker = "aiip_click_timer"
    if marker in text:
        return text
    script = """
<script id="aiip_click_timer">
(function(){
  const startedAt = Date.now();
  document.addEventListener("click", function(event) {
    const anchor = event.target && event.target.closest ? event.target.closest("a[href^='/go/']") : null;
    if (!anchor) return;
    try {
      const url = new URL(anchor.getAttribute("href"), window.location.origin);
      if (!url.searchParams.get("pls")) {
        url.searchParams.set("pls", Math.max(0, (Date.now() - startedAt) / 1000).toFixed(2));
        anchor.setAttribute("href", url.pathname + url.search + url.hash);
      }
    } catch (err) {}
  }, true);
})();
</script>
"""
    if "</body>" in text:
        return text.replace("</body>", script + "\n</body>", 1)
    return text + script


def resolve_target(row: pd.Series | dict) -> tuple[str, str, str]:
    approved = to_bool(row.get("approved")) or str(row.get("affiliate_status", "")).strip().lower() == "approved"
    affiliate_url = str(row.get("affiliate_url", "")).strip()
    official_url = str(row.get("official_url", "")).strip()
    if approved and affiliate_url:
        return affiliate_url, "affiliate_click", ""
    if official_url:
        return official_url, "official_click", "Liên kết tiếp thị đang chờ phê duyệt."
    return "", "unknown_click", "Chưa có affiliate_url hoặc official_url. Không thể redirect an toàn."


def go_page_html(slug: str, name: str, target_url: str, event_type: str, note: str) -> str:
    safe_target = html.escape(target_url, quote=True)
    safe_name = html.escape(name)
    safe_note = html.escape(note)
    payload = {
        "tool_slug": slug,
        "tool_name": name,
        "target_url": target_url,
        "event_type": event_type,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    fallback_webhook_json = json.dumps(settings.click_webhook_url)
    redirect_script = ""
    if target_url:
        redirect_script = f"""
<script>
(function(){{
  const params = new URLSearchParams(window.location.search);
  const sessionKey = "aiip_session_id";
  let sessionId = "";
  try {{
    sessionId = localStorage.getItem(sessionKey) || "";
    if (!sessionId) {{
      sessionId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : ("s_" + Date.now() + "_" + Math.random().toString(16).slice(2));
      localStorage.setItem(sessionKey, sessionId);
    }}
  }} catch (err) {{
    sessionId = "s_" + Date.now() + "_" + Math.random().toString(16).slice(2);
  }}
  const clickId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : ("c_" + Date.now() + "_" + Math.random().toString(16).slice(2));
  const userAgentHint = getUserAgentHint();
  const pageLoadSeconds = params.get("pls") || "";
  const fallbackWebhookUrl = {fallback_webhook_json};
  const trackingStatus = {{
    webhook_url_configured: Boolean(fallbackWebhookUrl),
    webhook_status: fallbackWebhookUrl ? "pending" : "not_configured",
    function_status: "not_started"
  }};
  const event = Object.assign({payload_json}, {{
    timestamp: new Date().toISOString(),
    session_id: sessionId,
    click_id: clickId,
    source_page: params.get("src") || "",
    source_page_type: pageType(params.get("src") || ""),
    cta_label: params.get("cta") || "",
    referrer: document.referrer || "",
    page_load_seconds: pageLoadSeconds,
    user_agent_hint: userAgentHint,
  }});
  try {{
    const key = "aiip_click_events";
    const events = JSON.parse(localStorage.getItem(key) || "[]");
    const classified = classifyClick(event, events);
    classified.cta = classified.cta_label;
    events.push(classified);
    localStorage.setItem(key, JSON.stringify(events.slice(-500)));
    sendTrackingEvent(classified);
    renderDebug(classified);
  }} catch (err) {{}}
  if (params.get("debug") !== "1") {{
    redirectAfterTracking();
  }}
  function sendTrackingEvent(event) {{
    const jobs = [];
    if (fallbackWebhookUrl) {{
      jobs.push(sendDirectWebhook(event, "primary_webhook"));
    }}
    try {{
      trackingStatus.function_status = "pending";
      jobs.push(fetch("/.netlify/functions/track-click", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(event),
        keepalive: true
      }}).then(function(response) {{
        trackingStatus.function_status = String(response.status);
        if (!response.ok && !fallbackWebhookUrl) return sendDirectWebhook(event, "function_http_" + response.status);
        return response;
      }}).catch(function() {{
        trackingStatus.function_status = "failed";
        if (!fallbackWebhookUrl) return sendDirectWebhook(event, "function_failed");
        return null;
      }}).finally(function() {{
        renderDebug(event);
      }}));
    }} catch (err) {{
      trackingStatus.function_status = "exception";
      if (!fallbackWebhookUrl) jobs.push(sendDirectWebhook(event, "function_exception"));
    }}
    if (!jobs.length) {{
      trackingStatus.webhook_status = "not_configured";
      window.aiipTrackPromise = Promise.resolve(null);
      renderDebug(event);
      return;
    }}
    window.aiipTrackPromise = Promise.allSettled(jobs).finally(function() {{ renderDebug(event); }});
  }}
  function sendDirectWebhook(event, reason) {{
    if (!fallbackWebhookUrl) {{
      trackingStatus.webhook_status = "not_configured";
      return Promise.resolve(null);
    }}
    try {{
      const payload = Object.assign({{}}, event, {{ fallback_reason: reason }});
      return fetch(fallbackWebhookUrl, {{
        method: "POST",
        mode: "no-cors",
        headers: {{ "Content-Type": "text/plain;charset=utf-8" }},
        body: JSON.stringify(payload),
        keepalive: true
      }}).then(function(response) {{
        trackingStatus.webhook_status = "sent";
        return response;
      }}).catch(function() {{
        trackingStatus.webhook_status = "failed";
        return null;
      }});
    }} catch (err) {{
      trackingStatus.webhook_status = "exception";
      return Promise.resolve(null);
    }}
  }}
  function redirectAfterTracking() {{
    const target = {json.dumps(target_url)};
    const timeout = new Promise(function(resolve) {{ setTimeout(resolve, 700); }});
    Promise.race([window.aiipTrackPromise || Promise.resolve(null), timeout]).finally(function() {{
      window.location.replace(target);
    }});
  }}
  function renderDebug(event) {{
    if (params.get("debug") !== "1") return;
    const payloadEl = document.getElementById("debug-payload");
    const webhookConfiguredEl = document.getElementById("debug-webhook-configured");
    const webhookStatusEl = document.getElementById("debug-webhook-status");
    const functionStatusEl = document.getElementById("debug-function-status");
    const slugEl = document.getElementById("debug-tool-slug");
    const targetEl = document.getElementById("debug-target-url");
    const panelEl = document.getElementById("debug-panel");
    if (panelEl) panelEl.style.display = "block";
    if (slugEl) slugEl.textContent = event.tool_slug || "";
    if (targetEl) targetEl.textContent = event.target_url || "";
    if (webhookConfiguredEl) webhookConfiguredEl.textContent = trackingStatus.webhook_url_configured ? "true" : "false";
    if (webhookStatusEl) webhookStatusEl.textContent = trackingStatus.webhook_status || "";
    if (functionStatusEl) functionStatusEl.textContent = trackingStatus.function_status || "";
    if (payloadEl) payloadEl.textContent = JSON.stringify(event, null, 2);
  }}
  function pageType(src) {{
    if (src.indexOf("/comparisons/") === 0) return "comparison";
    if (src.indexOf("-pricing") > -1) return "pricing";
    if (src.indexOf("/best-") === 0 || src.indexOf("best-") > -1) return "toplist";
    if (src === "/" || src === "") return "unknown";
    return "review";
  }}
  function getUserAgentHint() {{
    try {{
      if (navigator.userAgentData && navigator.userAgentData.brands) {{
        return navigator.userAgentData.brands.map(function(b) {{ return b.brand + "/" + b.version; }}).join(", ").slice(0, 120);
      }}
      return String(navigator.userAgent || "").slice(0, 120);
    }} catch (err) {{
      return "";
    }}
  }}
  function classifyClick(event, history) {{
    const reasons = [];
    let score = 100;
    const pageLoad = parseFloat(event.page_load_seconds || "");
    if (!Number.isNaN(pageLoad) && pageLoad < 2) {{
      reasons.push("page_load_under_2_seconds");
      score -= 30;
    }}
    if (!event.source_page || !event.referrer) {{
      reasons.push("missing_source_or_referrer");
      score -= 15;
    }}
    const ua = String(event.user_agent_hint || "").toLowerCase();
    if (ua.length < 4 || ["curl", "wget", "python-requests", "scrapy", "spider", "crawler", "headless"].some(function(x) {{ return ua.indexOf(x) !== -1; }})) {{
      reasons.push("unusual_user_agent");
      score -= 20;
    }}
    const now = Date.parse(event.timestamp);
    const recent = (history || []).filter(function(item) {{
      return item.session_id === event.session_id && Date.parse(item.timestamp || "") >= now - 5 * 60 * 1000;
    }});
    const sameTool = recent.filter(function(item) {{ return item.tool_slug === event.tool_slug; }}).length;
    if (sameTool >= 3) {{
      reasons.push("same_tool_more_than_3_clicks_in_5_minutes");
      score -= 35;
    }}
    const uniqueTools = Array.from(new Set(recent.map(function(item) {{ return item.tool_slug; }}).filter(Boolean)));
    if (recent.length >= 4 && uniqueTools.length >= 4) {{
      reasons.push("many_tools_clicked_quickly");
      score -= 25;
    }}
    score = Math.max(0, Math.min(100, score));
    event.click_quality_score = String(score);
    event.is_suspicious = (score < 60 || reasons.length > 0) ? "true" : "false";
    event.suspicious_reason = reasons.filter(function(v, i, arr) {{ return arr.indexOf(v) === i; }}).join("; ");
    return event;
  }}
}})();
</script>"""
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,follow">
  <title>Redirect to {safe_name} - {html.escape(settings.site_name)}</title>
  <meta name="description" content="Safe outbound redirect page for {safe_name}.">
  <style>body{{font-family:Arial,Helvetica,sans-serif;background:#f7f9fc;color:#17202a;line-height:1.6;margin:0}}.wrap{{max-width:760px;margin:10vh auto;padding:24px}}.card{{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:22px}}.btn{{display:inline-block;background:#0f766e;color:#fff;text-decoration:none;padding:11px 15px;border-radius:6px;font-weight:800}}</style>
{redirect_script}
</head>
<body><main class="wrap"><section class="card">
  <h1>Đang chuyển tới {safe_name}</h1>
  <p>{safe_note or "Click được ghi nhận ở trình duyệt và bạn sẽ được chuyển tiếp an toàn."}</p>
  <div id="debug-panel" style="display:none;background:#eef6ff;border:1px solid #cfe2ff;border-radius:8px;padding:12px;margin:14px 0">
    <strong>Debug mode</strong>
    <p>tool_slug: <code id="debug-tool-slug">{html.escape(slug)}</code></p>
    <p>target_url: <code id="debug-target-url">{safe_target}</code></p>
    <p>webhook_url_configured: <code id="debug-webhook-configured">false</code></p>
    <p>webhook_status: <code id="debug-webhook-status">waiting</code></p>
    <p>function_status: <code id="debug-function-status">waiting</code></p>
    <pre id="debug-payload" style="white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;overflow:auto">Payload will appear when debug=1.</pre>
  </div>
  {f'<p><a class="btn" rel="nofollow sponsored" href="{safe_target}">Tiếp tục tới {safe_name}</a></p>' if target_url else '<p>Thiếu URL đích. Vui lòng cập nhật affiliate_links.csv.</p>'}
  <p style="color:#64748b">Trang này không lưu IP, email, cookie cá nhân hoặc thông tin định danh cá nhân.</p>
</section></main></body></html>"""


def ensure_affiliate_tracking_files() -> None:
    ensure_click_events()
    links = load_affiliate_links()
    save_affiliate_links(links)


def run_affiliate_tracking_engine(output: Path | None = None) -> dict[str, int]:
    """Build local-safe tracking reports and static /go/<tracking_id>/ pages."""
    output_dir = output or settings.site_output_dir
    report = build_affiliate_tracking_report()
    redirect_map = build_redirect_map(report)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(settings.data_dir / "affiliate_tracking_report.csv", index=False, encoding="utf-8-sig")
    redirect_map.to_csv(settings.data_dir / "redirect_map.csv", index=False, encoding="utf-8-sig")
    pages = generate_tracking_redirect_pages(output_dir, redirect_map)
    return {"tracking_links": len(report), "redirect_rows": len(redirect_map), "redirect_pages": pages}


def build_affiliate_tracking_report() -> pd.DataFrame:
    source_path = settings.data_dir / "link_tracking_map.csv"
    if not source_path.exists():
        return pd.DataFrame(columns=AFFILIATE_TRACKING_REPORT_COLUMNS)
    tracking_map = pd.read_csv(source_path).fillna("")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in tracking_map.iterrows():
        platform = str(row.get("platform", "")).strip()
        post_id = str(row.get("post_id", "")).strip() or f"post-{index + 1:03d}"
        target_url = str(row.get("target_url", "")).strip()
        tracked_url = normalize_tracked_url(str(row.get("tracked_url", "") or target_url).strip(), platform, row)
        source = platform_source(platform)
        medium = medium_for_source(source, target_url)
        campaign = str(row.get("campaign", "")).strip() or campaign_from_url_or_topic(target_url, str(row.get("topic", "")))
        content = str(row.get("content_angle", "") or post_id).strip()
        page_slug = page_slug_from_url(target_url)
        topic = str(row.get("topic", "")).strip() or page_slug.replace("-", " ")
        tool_name = detect_tool_name(f"{target_url} {topic} {campaign}")
        base_tracking_id = slugify("-".join([page_slug or "page", source or "seo", post_id]))
        tracking_id = unique_tracking_id(base_tracking_id, seen)
        status = "ready" if target_url and tracked_url else "needs_review"
        rows.append(
            {
                "tracking_id": tracking_id,
                "source": source,
                "medium": medium,
                "campaign": campaign,
                "content": content,
                "platform": platform,
                "target_url": target_url,
                "tracked_url": tracked_url,
                "page_slug": page_slug,
                "topic": topic,
                "tool_name": tool_name,
                "status": status,
                "recommendation": tracking_recommendation(target_url, tracked_url, tool_name, source, content),
            }
        )
    return pd.DataFrame(rows, columns=AFFILIATE_TRACKING_REPORT_COLUMNS)


def build_redirect_map(report: pd.DataFrame) -> pd.DataFrame:
    if report.empty:
        return pd.DataFrame(columns=REDIRECT_MAP_COLUMNS)
    rows = []
    for _, row in report.iterrows():
        tracking_id = str(row.get("tracking_id", "")).strip()
        rows.append(
            {
                "tracking_id": tracking_id,
                "source": row.get("source", ""),
                "medium": row.get("medium", ""),
                "campaign": row.get("campaign", ""),
                "content": row.get("content", ""),
                "platform": row.get("platform", ""),
                "target_url": row.get("target_url", ""),
                "tracked_url": row.get("tracked_url", ""),
                "redirect_path": f"/go/{tracking_id}/" if tracking_id else "",
                "status": row.get("status", "needs_review"),
            }
        )
    return pd.DataFrame(rows, columns=REDIRECT_MAP_COLUMNS)


def generate_tracking_redirect_pages(output: Path, redirect_map: pd.DataFrame) -> int:
    if redirect_map.empty:
        return 0
    go_root = output / "go"
    go_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for _, row in redirect_map.iterrows():
        tracking_id = str(row.get("tracking_id", "")).strip()
        tracked_url = str(row.get("tracked_url", "")).strip()
        if not tracking_id or not tracked_url:
            continue
        folder = go_root / tracking_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(tracking_redirect_html(row), encoding="utf-8")
        count += 1
    return count


def tracking_redirect_html(row: pd.Series | dict) -> str:
    tracking_id = str(row.get("tracking_id", "")).strip()
    tracked_url = str(row.get("tracked_url", "")).strip()
    safe_url = html.escape(tracked_url, quote=True)
    safe_id = html.escape(tracking_id)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta http-equiv="refresh" content="0; url={safe_url}">
  <title>Continue - {safe_id}</title>
  <meta name="description" content="Local-safe tracking redirect.">
  <style>body{{font-family:Arial,Helvetica,sans-serif;background:#f8fafc;color:#0f172a;margin:0}}main{{max-width:720px;margin:12vh auto;padding:24px}}.card{{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:24px}}a{{color:#0f766e;font-weight:700}}</style>
  <script>window.location.replace({json.dumps(tracked_url)});</script>
</head>
<body>
  <main><section class="card">
    <h1>Continue to page</h1>
    <p>This tracking page does not store personal data. If you are not redirected, use the fallback link below.</p>
    <p><a rel="nofollow sponsored" href="{safe_url}">Continue to official page</a></p>
  </section></main>
</body>
</html>"""


def normalize_tracked_url(url: str, platform: str, row: pd.Series | dict) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme and url.startswith("/"):
        base = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
        url = base + url
        parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    source = platform_source(platform)
    campaign = str(row.get("campaign", "")).strip() or campaign_from_url_or_topic(url, str(row.get("topic", "")))
    content = str(row.get("post_id", "") or row.get("content_angle", "") or "content").strip()
    query.setdefault("utm_source", [source])
    query.setdefault("utm_medium", [medium_for_source(source, url)])
    query.setdefault("utm_campaign", [slugify(campaign) or "affiliate-content"])
    query.setdefault("utm_content", [slugify(content) or "social-post"])
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def platform_source(platform: str) -> str:
    text = str(platform or "").strip().lower()
    if "linkedin" in text:
        return "linkedin"
    if "facebook" in text:
        return "facebook"
    if "telegram" in text:
        return "telegram"
    if text in {"x", "twitter", "x/twitter"} or "twitter" in text:
        return "twitter"
    if text in {"seo", "article", "internal"}:
        return text
    return "seo"


def medium_for_source(source: str, target_url: str = "") -> str:
    if source in {"linkedin", "facebook", "twitter", "telegram"}:
        return "organic_social"
    if "/go/" in str(target_url):
        return "internal"
    return "article"


def campaign_from_url_or_topic(url: str, topic: str) -> str:
    slug = page_slug_from_url(url)
    if slug:
        return slug
    return slugify(topic) or "affiliate-content"


def page_slug_from_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    path = parsed.path.strip("/")
    if not path:
        return "homepage"
    parts = [part for part in path.split("/") if part]
    return parts[-1] if parts else "homepage"


def detect_tool_name(text: str) -> str:
    known = {
        "github-copilot": "GitHub Copilot",
        "github copilot": "GitHub Copilot",
        "cursor": "Cursor",
        "windsurf": "Windsurf",
        "codex": "Codex",
        "semrush": "Semrush",
        "surfer-seo": "Surfer SEO",
        "surfer seo": "Surfer SEO",
        "canva": "Canva",
        "make": "Make",
        "zapier": "Zapier",
        "elevenlabs": "ElevenLabs",
        "jasper": "Jasper",
        "copy-ai": "Copy.ai",
        "copy.ai": "Copy.ai",
    }
    lowered = str(text or "").lower()
    for key, value in known.items():
        if key in lowered:
            return value
    return ""


def tracking_recommendation(target_url: str, tracked_url: str, tool_name: str, source: str, content: str) -> str:
    if not target_url or not tracked_url:
        return "needs_better_cta"
    if not tool_name:
        return "missing_tool_name"
    if source in {"linkedin", "facebook", "twitter", "telegram"}:
        return "priority_social_push"
    if "comparison" in str(content).lower() or "vs" in str(target_url).lower():
        return "good_for_seo_internal_link"
    return "ready"


def unique_tracking_id(base: str, seen: set[str]) -> str:
    value = base or "tracking-link"
    if value not in seen:
        seen.add(value)
        return value
    index = 2
    while f"{value}-{index}" in seen:
        index += 1
    final = f"{value}-{index}"
    seen.add(final)
    return final
