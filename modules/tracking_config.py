from __future__ import annotations

import html
from pathlib import Path

from config import settings


def tracking_settings() -> dict[str, object]:
    """Return normalized tracking settings with safe defaults.

    This project is static-first. Empty IDs, missing webhooks, or disabled
    tracking must never break a local build or GitHub Pages deployment.
    """
    config = {}
    path = settings.base_dir / "config" / "tracking.json"
    if Path(path).exists():
        try:
            import json

            config = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            config = {}
    ga4 = (
        str(config.get("ga4_measurement_id") or config.get("GA4_MEASUREMENT_ID") or settings.ga_measurement_id)
        .strip()
    )
    verification = str(config.get("GOOGLE_SITE_VERIFICATION") or settings.google_site_verification).strip()
    return {
        "enable_tracking": settings.enable_tracking,
        "ga4_measurement_id": ga4,
        "google_site_verification": verification,
        "gsc_site_url": str(config.get("gsc_site_url") or settings.base_site_url or settings.site_domain).strip(),
        "tracking_mode": str(config.get("tracking_mode") or "local_safe").strip(),
        "click_collection_mode": str(config.get("click_collection_mode") or "static_go_pages").strip(),
        "webhook_url": str(config.get("webhook_url") or settings.click_webhook_url).strip(),
        "enable_go_tracking": str(config.get("enable_go_tracking", True)).strip().lower() in {"1", "true", "yes", "on"},
        "enable_utm_tracking": str(config.get("enable_utm_tracking", True)).strip().lower() in {"1", "true", "yes", "on"},
    }


def analytics_snippet() -> str:
    """Return optional GA4 + local click instrumentation.

    The script is inert until ENABLE_TRACKING is true and a GA4 measurement ID is
    configured. It never stores personal data and only sends aggregate click
    events through gtag when the site owner opts in.
    """
    config = tracking_settings()
    if not config["enable_tracking"]:
        return "<!-- Tracking disabled in config/tracking.json. -->"

    measurement = str(config["ga4_measurement_id"]).strip()
    if not measurement:
        return "<!-- Tracking enabled but GA4_MEASUREMENT_ID is empty. -->"

    safe_id = html.escape(measurement, quote=True)
    return f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={safe_id}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{safe_id}');
document.addEventListener('click', function(event) {{
  const link = event.target.closest && event.target.closest('a[href]');
  if (!link || !window.gtag) return;
  const href = link.getAttribute('href') || '';
  let eventName = 'internal_link_click';
  if (href.indexOf('/go/') === 0) eventName = 'cta_go_click';
  if (link.closest('.language-switcher')) eventName = 'language_switch_click';
  if (eventName === 'internal_link_click' && href.indexOf('/') !== 0) return;
  gtag('event', eventName, {{
    link_url: href,
    link_text: (link.textContent || '').trim().slice(0, 80),
    page_path: window.location.pathname
  }});
}}, true);
</script>"""
