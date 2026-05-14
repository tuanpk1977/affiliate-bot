from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

LANDING_ROOT = "landing_pages"
LANDING_INDEX_OUTPUT = "data/output/landing_pages_index.csv"


def build_landing_pages(plan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    root = Path(LANDING_ROOT)
    root.mkdir(exist_ok=True)

    for _, row in plan.iterrows():
        brand = str(row.get("brand_name", "")).strip()
        if not brand:
            continue

        slug = slugify(brand)
        page_dir = root / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / "index.html"

        page_path.write_text(build_landing_html(row), encoding="utf-8")
        rows.append(
            {
                "brand_name": brand,
                "slug": slug,
                "local_file": str(page_path),
                "recommended_url": row.get("recommended_landing_page_url", ""),
                "affiliate_url": row.get("affiliate_url", ""),
                "status": "created",
                "manual_before_publish": row.get("manual_before_upload", ""),
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(LANDING_INDEX_OUTPUT, index=False)
    return df


def build_landing_html(row: pd.Series) -> str:
    brand = str(row.get("brand_name", "")).strip()
    category = str(row.get("category", "")).strip()
    affiliate_url = str(row.get("affiliate_url", "")).strip() or "#"
    keywords = str(row.get("keywords", "")).replace(" | ", ", ")
    risk = str(row.get("ads_policy_risk", "")).strip()
    google = str(row.get("google_ads_precheck", "")).strip()
    microsoft = str(row.get("microsoft_ads_precheck", "")).strip()

    safe_brand = html.escape(brand)
    safe_affiliate_url = html.escape(affiliate_url, quote=True)

    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_brand} Review - Thông tin trước khi đăng ký</title>
  <meta name="description" content="Review {safe_brand}: thông tin affiliate, ưu nhược điểm, điều khoản cần kiểm tra và link đăng ký.">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --text: #18202a;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --accent: #0f766e;
      --warn: #9a3412;
      --card: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    header, main, footer {{
      max-width: 960px;
      margin: 0 auto;
      padding: 28px 18px;
    }}
    header {{
      padding-top: 44px;
    }}
    h1 {{
      font-size: 34px;
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 22px;
      margin: 32px 0 12px;
    }}
    p, li {{
      color: var(--muted);
      font-size: 16px;
    }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin: 18px 0;
    }}
    .cta {{
      display: inline-block;
      background: var(--accent);
      color: #fff;
      text-decoration: none;
      padding: 12px 18px;
      border-radius: 6px;
      font-weight: 700;
      margin-top: 8px;
    }}
    .notice {{
      border-left: 4px solid var(--warn);
      padding-left: 14px;
      color: var(--warn);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }}
    footer {{
      border-top: 1px solid var(--line);
      margin-top: 28px;
      font-size: 14px;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <header>
    <h1>{safe_brand} Review</h1>
    <p>Trang này tổng hợp thông tin để bạn tự đánh giá trước khi đăng ký hoặc tham gia chương trình affiliate.</p>
    <a class="cta" href="{safe_affiliate_url}" rel="nofollow sponsored">Xem trang chính thức</a>
  </header>
  <main>
    <section class="panel">
      <h2>Tóm tắt nhanh</h2>
      <p><strong>Ngành:</strong> {html.escape(category or "chưa phân loại")}</p>
      <p><strong>Keyword tham khảo:</strong> {html.escape(keywords or "chưa có keyword")}</p>
      <p><strong>Rủi ro quảng cáo:</strong> {html.escape(risk or "chưa rõ")}</p>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Điểm mạnh</h2>
        <ul>
          <li>Có tín hiệu affiliate đáng kiểm tra.</li>
          <li>Có thể dùng làm lead để nghiên cứu hoặc đóng gói thông tin.</li>
          <li>Có thể tạo nội dung review/so sánh trước khi gửi traffic.</li>
        </ul>
      </div>
      <div class="panel">
        <h2>Điểm cần kiểm tra</h2>
        <ul>
          <li>Mức hoa hồng và thời gian cookie có còn đúng không.</li>
          <li>Affiliate terms có cho phép paid search/PPC không.</li>
          <li>Có cấm brand bidding hoặc direct linking không.</li>
        </ul>
      </div>
    </section>

    <section class="panel">
      <h2>Lưu ý trước khi chạy ads</h2>
      <p><strong>Google Ads:</strong> {html.escape(google or "cần kiểm tra thủ công")}</p>
      <p><strong>Bing/Microsoft Ads:</strong> {html.escape(microsoft or "cần kiểm tra thủ công")}</p>
      <p class="notice">Không cam kết lợi nhuận. Với crypto/trading/finance, cần kiểm tra chứng nhận, pháp lý và thị trường được phép trước khi quảng cáo.</p>
    </section>

    <section class="panel">
      <h2>Disclosure affiliate</h2>
      <p>Trang này có thể chứa link affiliate. Nếu bạn đăng ký qua link trên trang, chủ website có thể nhận hoa hồng. Điều này không làm thay đổi chi phí của bạn.</p>
    </section>

    <section class="panel">
      <h2>Privacy Policy, Terms, Contact</h2>
      <p>Trước khi publish, hãy thay phần này bằng Privacy Policy, Terms và thông tin liên hệ thật của website bạn.</p>
    </section>
  </main>
  <footer>
    <p>Last updated: generated by Affiliate Research Bot.</p>
  </footer>
</body>
</html>
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "affiliate-lead"
