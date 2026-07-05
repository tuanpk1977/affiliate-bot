from __future__ import annotations

import html
from pathlib import Path

from config import settings
from modules.indexing_policy import REDIRECT_ROBOTS_META


PAGES = {
    "crm-alternatives": {
        "title": "Lua chon CRM thay the 2026",
        "description": "So sanh cac lua chon CRM thay the cho doanh nghiep nho, doi ban hang va marketing truoc khi chon nen tang.",
        "intro": "Trang nay giup ban lap danh sach rut gon cac nen tang CRM theo nhu cau thuc te. Hay kiem tra gia, gioi han nguoi dung, tu dong hoa, tich hop va dieu khoan moi nhat tren website chinh thuc truoc khi mua.",
        "sections": [
            ("Khi nao nen tim CRM thay the?", "Nen can nhac doi CRM khi chi phi tang nhanh, quy trinh ban hang kho tuy chinh, bao cao khong du ro hoac doi ngu phai dung qua nhieu cong cu bo sung."),
            ("Cac lua chon nen xem xet", "HubSpot phu hop voi doi ngu can CRM ket hop marketing. Pipedrive tap trung vao pipeline ban hang. ActiveCampaign phu hop khi email automation la phan quan trong cua quy trinh."),
            ("Cach chon nen tang", "So sanh tong chi phi, so luong nguoi dung, tich hop, kha nang xuat du lieu, ho tro va thoi gian trien khai. Khong nen chon chi dua tren danh sach tinh nang."),
        ],
        "links": [
            ("/vi/best-crm-tools/", "Cong cu CRM tot nhat"),
            ("/vi/category/crm-tools/", "Danh muc CRM"),
            ("/vi/hub/crm/", "Trung tam noi dung CRM"),
            ("/vi/review/hubspot/", "Danh gia HubSpot"),
            ("/vi/review/pipedrive/", "Danh gia Pipedrive"),
        ],
    },
    "marketing-software-review": {
        "title": "Danh gia phan mem marketing 2026",
        "description": "Huong dan danh gia phan mem marketing theo email, CRM, automation, bao cao va muc phu hop quy trinh.",
        "intro": "Phan mem marketing tot nhat phu thuoc vao kenh, quy mo doi ngu va muc do tu dong hoa can thiet. Trang nay trinh bay cach danh gia cong cu ma khong dua vao quang cao hoac tuyen bo chua duoc xac minh.",
        "sections": [
            ("Nen danh gia nhung gi?", "Kiem tra email marketing, CRM, automation, bao cao, quan ly chien dich, tich hop va kha nang xuat du lieu. Gia va gioi han su dung can duoc xac minh tren website chinh thuc."),
            ("Phu hop nhat cho ai?", "Doanh nghiep nho thuong can cong cu de trien khai. Doi marketing lon can phan quyen, bao cao va tich hop sau hon. Nguoi sang tao noi dung co the uu tien email va landing page."),
            ("Rui ro can kiem tra", "Chi phi co the tang theo so lien he, so nguoi dung hoac muc su dung. Hay kiem tra chinh sach gui email, gioi han automation, ho tro va dieu khoan huy dich vu."),
        ],
        "links": [
            ("/vi/email-marketing-software-review/", "Danh gia phan mem email marketing"),
            ("/vi/marketing-alternatives/", "Cac lua chon thay the marketing"),
            ("/vi/hub/marketing/", "Trung tam noi dung marketing"),
            ("/vi/review/activecampaign/", "Danh gia ActiveCampaign"),
            ("/vi/category/email-marketing-tools/", "Danh muc email marketing"),
        ],
    },
}


def write_gsc_404_recovery_pages(output: Path | None = None) -> list[Path]:
    root = output or settings.site_output_dir
    written: list[Path] = []
    for slug, page in PAGES.items():
        target = root / "vi" / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_page(slug, page), encoding="utf-8")
        written.append(target)
    return written


def render_page(slug: str, page: dict) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    canonical = f"{base}/vi/{slug}/"
    links = "".join(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></li>' for url, label in page["links"])
    sections = "".join(f"<section class='card'><h2>{html.escape(title)}</h2><p>{html.escape(body)}</p></section>" for title, body in page["sections"])
    contact = settings.contact_email or "contact@smileaireviewhub.com"
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page["title"])} | {html.escape(settings.site_name)}</title>
<meta name="description" content="{html.escape(page["description"], quote=True)}">
<meta name="robots" content="{REDIRECT_ROBOTS_META}">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
<link rel="alternate" hreflang="vi" href="{html.escape(canonical, quote=True)}">
<link rel="alternate" hreflang="x-default" href="{html.escape(canonical, quote=True)}">
<style>{css()}</style>
</head>
<body>
<nav><div class="wrap"><a href="/vi/"><strong>{html.escape(settings.site_name)}</strong></a><a href="/vi/reviews/">Danh gia</a><a href="/vi/comparisons/">So sanh</a><a href="/vi/categories/">Danh muc</a><a href="/vi/contact/">Lien he</a></div></nav>
<main class="wrap">
<article>
<header class="card"><p class="eyebrow">Huong dan nghien cuu 2026</p><h1>{html.escape(page["title"])}</h1><p>{html.escape(page["intro"])}</p></header>
{sections}
<section class="card"><h2>Noi dung lien quan</h2><ul>{links}</ul></section>
<section class="card"><h2>Ket luan</h2><p>Dung trang nay de tao danh sach rut gon, sau do xac minh gia, tinh nang, gioi han va dieu khoan moi nhat truc tiep voi nha cung cap.</p></section>
</article>
</main>
<footer><div class="wrap"><p><strong>{html.escape(settings.site_name)}</strong></p><p>Contact: <!--email_off--><a href="mailto:{html.escape(contact, quote=True)}">{html.escape(contact)}</a><!--/email_off--></p><a href="/vi/about/">Gioi thieu</a><a href="/vi/contact/">Lien he</a><a href="/vi/editorial-policy/">Chinh sach bien tap</a></div></footer>
</body>
</html>"""


def css() -> str:
    return """*{box-sizing:border-box}body{margin:0;background:#f7f9fc;color:#17202a;font-family:Arial,sans-serif;line-height:1.7}.wrap{max-width:960px;margin:auto;padding:0 20px}nav{background:#fff;border-bottom:1px solid #dbe3ef;padding:18px 0}nav a,footer a{margin-right:18px;color:#0f766e;text-decoration:none}.card{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:22px;margin:20px 0}.eyebrow{color:#0f766e;font-weight:700}h1{font-size:38px;line-height:1.2}h2{font-size:25px}li{margin:8px 0}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0}@media(max-width:700px){h1{font-size:30px}nav a{display:inline-block;margin-bottom:8px}}"""
