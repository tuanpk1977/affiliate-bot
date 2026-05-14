from __future__ import annotations

import re

import pandas as pd

AD_PLAN_OUTPUT = "data/output/ad_launch_plan.csv"
GOOGLE_ADS_TEMPLATE = "data/output/google_ads_upload_template.csv"
MICROSOFT_ADS_TEMPLATE = "data/output/microsoft_ads_upload_template.csv"
ADS_MANUAL_STEPS = "data/output/ads_manual_steps.txt"


def build_ad_outputs(df: pd.DataFrame) -> dict[str, pd.DataFrame | str]:
    eligible = select_ad_candidates(df)
    plan = build_ad_launch_plan(eligible)
    google_template = build_ads_upload_template(plan, platform="google")
    microsoft_template = build_ads_upload_template(plan, platform="microsoft")
    manual_steps = build_manual_steps(plan)

    plan.to_csv(AD_PLAN_OUTPUT, index=False)
    google_template.to_csv(GOOGLE_ADS_TEMPLATE, index=False)
    microsoft_template.to_csv(MICROSOFT_ADS_TEMPLATE, index=False)
    with open(ADS_MANUAL_STEPS, "w", encoding="utf-8") as file:
        file.write(manual_steps)

    return {
        "plan": plan,
        "google_template": google_template,
        "microsoft_template": microsoft_template,
        "manual_steps": manual_steps,
    }


def select_ad_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    allowed_statuses = {"prepare_ad_test_after_terms_check", "manual_terms_check_required"}
    blocked_statuses = {"blocked_by_ads_compliance", "not_ready_for_ads"}
    result = df[
        df["ads_status"].isin(allowed_statuses)
        & ~df["ads_status"].isin(blocked_statuses)
        & ~df["ads_policy_risk"].isin(["high"])
    ].copy()
    return result.sort_values(
        ["total_score", "ad_readiness_score", "economics_score"],
        ascending=[False, False, False],
    ).head(20)


def build_ad_launch_plan(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        brand = str(row.get("brand_name", "")).strip()
        category = str(row.get("category", "")).strip()
        landing_slug = slugify(brand)
        landing_url = f"https://YOUR-DOMAIN.com/review/{landing_slug}"
        rows.append(
            {
                "brand_name": brand,
                "category": category,
                "affiliate_url": row.get("affiliate_url", ""),
                "recommended_landing_page_url": landing_url,
                "google_ads_precheck": row.get("google_ads_precheck", ""),
                "microsoft_ads_precheck": row.get("microsoft_ads_precheck", ""),
                "ads_policy_risk": row.get("ads_policy_risk", ""),
                "campaign_name": f"AFF - {brand} - Search Test",
                "ad_group_name": f"{brand} affiliate review",
                "daily_budget_suggestion": "5-20 USD khi mới test",
                "landing_page_must_have": landing_page_requirements(row),
                "keywords": build_keywords(brand, category),
                "negative_keywords": "free money, guaranteed profit, scam, hack, crack, pirated",
                "headline_1": fit_text(f"{brand} Review", 30),
                "headline_2": fit_text("So sánh trước khi đăng ký", 30),
                "headline_3": fit_text("Xem phí và ưu nhược điểm", 30),
                "description_1": fit_text(
                    f"Tìm hiểu {brand}, hoa hồng, ưu nhược điểm và điều khoản trước khi tham gia.",
                    90,
                ),
                "description_2": fit_text(
                    "Bài review có disclosure affiliate, thông tin rõ ràng và không cam kết lợi nhuận.",
                    90,
                ),
                "manual_before_upload": manual_before_upload(row),
            }
        )
    return pd.DataFrame(rows)


def build_ads_upload_template(plan: pd.DataFrame, platform: str) -> pd.DataFrame:
    rows = []
    for _, row in plan.iterrows():
        for keyword in str(row.get("keywords", "")).split(" | "):
            rows.append(
                {
                    "Campaign": row.get("campaign_name", ""),
                    "Ad Group": row.get("ad_group_name", ""),
                    "Keyword": keyword,
                    "Match Type": "Phrase",
                    "Final URL": row.get("recommended_landing_page_url", ""),
                    "Headline 1": row.get("headline_1", ""),
                    "Headline 2": row.get("headline_2", ""),
                    "Headline 3": row.get("headline_3", ""),
                    "Description 1": row.get("description_1", ""),
                    "Description 2": row.get("description_2", ""),
                    "Platform": "Google Ads" if platform == "google" else "Microsoft/Bing Ads",
                    "Status": "PAUSED - cần kiểm tra thủ công trước khi bật",
                }
            )
    return pd.DataFrame(rows)


def build_manual_steps(plan: pd.DataFrame) -> str:
    lines = [
        "HƯỚNG DẪN CHẠY ADS SAU KHI BOT LỌC LEAD",
        "",
        "Bot đã làm tự động:",
        "- Tìm lead affiliate từ source cấu hình.",
        "- Chấm điểm lead.",
        "- Kiểm tra rủi ro Google Ads / Bing Ads cơ bản.",
        "- Loại lead rủi ro cao khỏi file upload ads.",
        "- Tạo kế hoạch landing page và mẫu import quảng cáo.",
        "",
        "Bạn cần làm thủ công trước khi chạy thật:",
        "1. Mở ad_launch_plan.csv.",
        "2. Chọn 1 dự án OK.",
        "3. Copy affiliate_url của dự án đó.",
        "4. Tạo landing page trên domain của bạn theo cột recommended_landing_page_url.",
        "5. Trên landing page phải có review/thông tin thật, ưu nhược điểm, disclosure affiliate, Privacy Policy, Terms, Contact.",
        "6. Không dùng landing page chỉ có mỗi nút bấm qua link affiliate.",
        "7. Kiểm tra lại affiliate terms có cho phép Google Ads/Bing Ads/PPC/brand bidding không.",
        "8. Với crypto/trading/finance: không chạy nếu chưa có chứng nhận/phê duyệt và kiểm tra pháp lý theo quốc gia target.",
        "9. Khi đã kiểm tra xong, upload google_ads_upload_template.csv hoặc microsoft_ads_upload_template.csv, để campaign ở trạng thái PAUSED trước.",
        "10. Bật campaign với ngân sách nhỏ, theo dõi disapproval, search terms và conversion.",
        "",
        "File bot tạo:",
        "- data/output/ad_launch_plan.csv",
        "- data/output/google_ads_upload_template.csv",
        "- data/output/microsoft_ads_upload_template.csv",
        "",
    ]
    if plan.empty:
        lines.extend(
            [
                "Hiện chưa có lead nào đủ điều kiện đưa vào file ads template.",
                "Lý do thường gặp: rủi ro ads cao, crypto/trading cần certification, hoặc cần verify điều khoản thủ công.",
            ]
        )
    return "\n".join(lines)


def build_keywords(brand: str, category: str) -> str:
    base = [
        f"{brand} review",
        f"{brand} pricing",
        f"{brand} alternatives",
        f"{brand} affiliate",
    ]
    if category in {"marketplace", "ecommerce"}:
        base.extend([f"{brand} coupons", f"{brand} deals"])
    elif category in {"saas", "ai", "devtools", "dev tools"}:
        base.extend([f"{brand} software", f"{brand} comparison"])
    return " | ".join(dict.fromkeys(base))


def landing_page_requirements(row: pd.Series) -> str:
    return " | ".join(
        [
            "review hoặc phân tích thật",
            "affiliate disclosure rõ ràng",
            "ưu nhược điểm",
            "giá/phí nếu có",
            "Privacy Policy",
            "Terms",
            "Contact",
            "không claim lợi nhuận đảm bảo",
        ]
    )


def manual_before_upload(row: pd.Series) -> str:
    checks = [
        "thay YOUR-DOMAIN.com bằng domain thật",
        "dán affiliate link vào nút CTA trên landing page",
        "kiểm tra affiliate terms cho phép PPC/paid search",
        "không bid brand keyword nếu terms cấm",
        "kiểm tra landing page chạy được trên mobile",
    ]
    if str(row.get("ads_policy_risk", "")) == "medium":
        checks.append("kiểm tra thủ công disclosure/terms vì bot đánh dấu rủi ro trung bình")
    return " | ".join(checks)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "affiliate-lead"


def fit_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"
