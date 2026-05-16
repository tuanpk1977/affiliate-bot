from __future__ import annotations

import html

from config import settings


def analytics_snippet() -> str:
    """Return optional GA4 + local click instrumentation.

    The script is inert until ENABLE_TRACKING is true and a GA4 measurement ID is
    configured. It never stores personal data and only sends aggregate click
    events through gtag when the site owner opts in.
    """
    if not settings.enable_tracking:
        return "<!-- Tracking disabled in config/tracking.json. -->"

    measurement = settings.ga_measurement_id.strip()
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

