from __future__ import annotations

from typing import Optional

import pandas as pd
import requests

STATUS_VI = {
    "Premium lead": "Lead rất tốt",
    "Good lead": "Lead tốt",
    "Research more": "Cần nghiên cứu thêm",
    "Needs manual commission check": "Cần kiểm tra hoa hồng thủ công",
    "Low priority": "Chưa ưu tiên",
    "ready_for_verification": "Sẵn sàng xác minh",
    "needs_manual_review": "Cần kiểm tra thủ công",
    "research_more": "Cần nghiên cứu thêm",
    "watchlist": "Đưa vào danh sách theo dõi",
    "can_package_after_proof": "Có thể đóng gói bán sau khi có bằng chứng",
    "verify_before_selling": "Cần xác minh trước khi bán",
    "blocked_until_verified": "Đang bị chặn cho đến khi xác minh",
    "do_not_sell_yet": "Chưa nên bán",
    "prepare_ad_test_after_terms_check": "Có thể chuẩn bị test ads sau khi kiểm tra điều khoản",
    "manual_terms_check_required": "Cần kiểm tra điều khoản quảng cáo thủ công",
    "not_ready_for_ads": "Chưa sẵn sàng chạy ads",
    "blocked_by_ads_compliance": "Bị chặn do rủi ro chính sách quảng cáo",
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "auto_verified_paid_traffic_signal": "Bot thấy tín hiệu cho phép traffic trả phí",
    "auto_verified_low_risk": "Bot thấy rủi ro thấp",
    "needs_manual_ads_review": "Cần kiểm tra ads thủ công",
    "needs_platform_certification": "Cần chứng nhận/phê duyệt từ nền tảng ads",
    "failed_blocking_terms_found": "Bot phát hiện điều khoản chặn ads",
    "requires_google_certification_and_local_legal_review": "Cần chứng nhận Google và kiểm tra pháp lý theo quốc gia",
    "requires_microsoft_pre_approval_and_market_eligibility": "Cần Microsoft/Bing phê duyệt trước và kiểm tra thị trường được phép",
    "blocked_until_affiliate_terms_allow_paid_search": "Bị chặn cho đến khi affiliate terms cho phép paid search",
    "manual_landing_page_review_required": "Cần kiểm tra landing page thủ công",
    "eligible_for_compliant_landing_page_test": "Có thể test bằng landing page đúng chính sách",
}

CHECKLIST_VI = {
    "find official affiliate page": "Tìm trang affiliate chính thức",
    "open affiliate page and confirm program is active": "Mở trang affiliate và xác nhận chương trình còn hoạt động",
    "confirm commission rate": "Xác nhận mức hoa hồng",
    "confirm recurring duration and cancellation rules": "Xác nhận thời hạn recurring và điều kiện hủy",
    "confirm cookie window": "Xác nhận thời gian cookie",
    "confirm payout method and payout schedule": "Xác nhận phương thức và lịch thanh toán",
    "check terms, privacy, and affiliate restrictions": "Kiểm tra điều khoản, quyền riêng tư và hạn chế affiliate",
    "check site availability": "Kiểm tra website còn truy cập được",
    "capture proof screenshot before selling": "Chụp bằng chứng trước khi bán thông tin",
    "record allowed traffic sources before ads": "Ghi lại nguồn traffic được phép trước khi chạy ads",
}

FINDING_VI = {
    "paid search prohibited": "Cấm paid search",
    "ppc prohibited": "Cấm PPC",
    "google ads prohibited": "Cấm Google Ads",
    "bing ads prohibited": "Cấm Bing/Microsoft Ads",
    "trademark bidding prohibited": "Cấm đấu thầu từ khóa thương hiệu",
    "direct linking prohibited": "Cấm direct linking",
}


def build_top_report(df: pd.DataFrame, top_n: int = 10) -> str:
    if df.empty:
        return "Không có dữ liệu để báo cáo."

    top = sort_leads(df).head(top_n)
    lines = ["TOP LEAD AFFILIATE"]
    for index, (_, row) in enumerate(top.iterrows(), start=1):
        lines.extend(
            [
                "",
                f"{index}. {row.get('brand_name', '')} - {vi(row.get('verdict', ''))}",
                f"   Website: {row.get('website', '')}",
                f"   Ngành: {vi_category(row.get('category', ''))}",
                f"   Nguồn: {row.get('source', '')} | Ghi chú: {row.get('notes', '')}",
                f"   Tổng điểm: {row.get('total_score', '')} | Chất lượng lead: {row.get('affiliate_quality_score', '')} | Giá trị để bán: {row.get('data_product_value_score', '')} | Độ sẵn sàng ads: {row.get('ad_readiness_score', '')}",
                f"   Hoa hồng: {row.get('commission_text', '') or 'chưa rõ'} | Cookie: {row.get('cookie_text', '') or 'chưa rõ'} | Loại: {vi_commission_type(row.get('commission_type', ''))}",
                f"   Link affiliate: {row.get('affiliate_url', '') or 'chưa tìm thấy'}",
                f"   Xác minh: {vi(row.get('review_status', ''))} | Bán lead: {vi(row.get('sale_status', ''))} | Ads: {vi(row.get('ads_status', ''))}",
                f"   Rủi ro ads: {vi(row.get('ads_policy_risk', ''))} | Bot verify: {vi(row.get('auto_verification_status', ''))}",
                f"   Google Ads: {vi(row.get('google_ads_precheck', ''))}",
                f"   Bing/Microsoft Ads: {vi(row.get('microsoft_ads_precheck', ''))}",
                f"   Nhóm khách nên bán: {vi_audience(row.get('target_audience', ''))}",
                f"   Góc bán: {vi_selling_angle(row.get('selling_angle', ''))}",
                f"   Đề xuất tiếp theo: {vi_action(row.get('recommended_action', ''))}",
            ]
        )
        checklist = str(row.get("verification_checklist", "")).strip()
        if checklist:
            lines.append(f"   Cần kiểm tra: {vi_checklist(checklist)}")
        findings = str(row.get("ads_policy_findings", "")).strip()
        if findings:
            lines.append(f"   Vấn đề ads phát hiện: {vi_findings(findings)}")
        recommendation = str(row.get("safe_ads_recommendation", "")).strip()
        if recommendation:
            lines.append(f"   Khuyến nghị ads: {vi_ads_recommendation(recommendation)}")
        reasoning = str(row.get("reasoning", "")).strip()
        if reasoning:
            lines.append(f"   Lý do bot chấm điểm: {vi_reasoning(reasoning)}")
    return "\n".join(lines).strip()


def build_decision_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "Không có dữ liệu để đánh giá."

    sorted_df = sort_leads(df)
    best_sell = sorted_df[
        sorted_df["sale_status"].isin(["can_package_after_proof", "verify_before_selling"])
    ]
    best_ads = sorted_df[
        sorted_df["ads_status"].isin(["prepare_ad_test_after_terms_check", "manual_terms_check_required"])
    ]
    needs_review = sorted_df[sorted_df["review_status"] == "needs_manual_review"]

    lines = [
        "TÓM TẮT QUYẾT ĐỊNH LEAD AFFILIATE",
        "",
        "Mục tiêu:",
        "- Tự tìm dự án affiliate tốt để bán thông tin cho người làm affiliate.",
        "- Lọc ra dự án có thể chuẩn bị chạy Google Ads / Bing Ads một cách đúng chính sách.",
        "",
    ]

    lines.extend(build_section("DỰ ÁN ĐÁNG BÁN THÔNG TIN NHẤT", best_sell))
    lines.extend(build_section("DỰ ÁN CÓ THỂ CHUẨN BỊ CHẠY ADS", best_ads))
    lines.extend(build_section("TOP CRYPTO / TRADING", sorted_df[sorted_df["category"].isin(["crypto", "trading"])]))
    lines.extend(build_section("TOP NỀN TẢNG MUA BÁN / MARKETPLACE", sorted_df[sorted_df["category"].isin(["marketplace", "ecommerce"])]))
    lines.extend(build_section("DỰ ÁN CẦN VERIFY TRƯỚC", needs_review))

    top = sorted_df.head(1)
    if not top.empty:
        row = top.iloc[0]
        lines.extend(
            [
                "",
                "KẾT LUẬN CỦA BOT:",
                f"- Ứng viên ưu tiên hiện tại: {row.get('brand_name', '')}",
                f"- Tổng điểm: {row.get('total_score', '')}",
                f"- Đánh giá: {vi(row.get('verdict', ''))}",
                f"- Trạng thái bán lead: {vi(row.get('sale_status', ''))}",
                f"- Trạng thái ads: {vi(row.get('ads_status', ''))}",
                f"- Google Ads: {vi(row.get('google_ads_precheck', ''))}",
                f"- Bing/Microsoft Ads: {vi(row.get('microsoft_ads_precheck', ''))}",
                f"- Đề xuất: {vi_action(row.get('recommended_action', ''))}",
                f"- Góc bán: {vi_selling_angle(row.get('selling_angle', ''))}",
            ]
        )

    return "\n".join(lines).strip()


def build_section(title: str, df: pd.DataFrame, limit: int = 5) -> list[str]:
    lines = ["", title]
    if df.empty:
        lines.append("- Chưa có ứng viên phù hợp.")
        return lines

    for index, (_, row) in enumerate(sort_leads(df).head(limit).iterrows(), start=1):
        lines.append(
            f"{index}. {row.get('brand_name', '')} | Tổng {row.get('total_score', '')} | "
            f"Chất lượng {row.get('affiliate_quality_score', '')} | Ads {row.get('ad_readiness_score', '')}"
        )
        lines.append(f"   Website: {row.get('website', '')}")
        lines.append(f"   Nguồn: {row.get('source', '')}")
        lines.append(f"   Link affiliate: {row.get('affiliate_url', '') or 'chưa tìm thấy'}")
        lines.append(f"   Bán lead: {vi(row.get('sale_status', ''))} | Ads: {vi(row.get('ads_status', ''))}")
        lines.append(f"   Rủi ro ads: {vi(row.get('ads_policy_risk', ''))} | Google: {vi(row.get('google_ads_precheck', ''))}")
        lines.append(f"   Đề xuất: {vi_action(row.get('recommended_action', ''))}")
        checklist = str(row.get("verification_checklist", "")).strip()
        if checklist:
            lines.append(f"   Cần kiểm tra: {vi_checklist(checklist)}")
    return lines


def sort_leads(df: pd.DataFrame) -> pd.DataFrame:
    sort_columns = [
        column
        for column in [
            "total_score",
            "economics_score",
            "commission_percent",
            "flat_commission_amount",
            "ad_readiness_score",
        ]
        if column in df.columns
    ]
    if not sort_columns:
        return df
    return df.sort_values(sort_columns, ascending=[False] * len(sort_columns))


def vi(value: object) -> str:
    text = str(value or "")
    return STATUS_VI.get(text, text)


def vi_category(value: object) -> str:
    mapping = {
        "ai": "AI",
        "saas": "SaaS/phần mềm",
        "crypto": "Crypto",
        "trading": "Trading",
        "marketplace": "Nền tảng mua bán/marketplace",
        "ecommerce": "Thương mại điện tử",
        "finance": "Tài chính",
        "marketing": "Marketing",
        "education": "Giáo dục",
    }
    return mapping.get(str(value or "").lower(), str(value or ""))


def vi_commission_type(value: object) -> str:
    mapping = {
        "recurring": "hoa hồng định kỳ",
        "flat": "hoa hồng cố định",
        "percentage": "hoa hồng theo phần trăm",
        "one-time": "hoa hồng một lần",
        "unknown": "chưa rõ",
    }
    return mapping.get(str(value or "").lower(), str(value or ""))


def vi_checklist(text: str) -> str:
    return " | ".join(CHECKLIST_VI.get(item.strip(), item.strip()) for item in text.split("|"))


def vi_findings(text: str) -> str:
    return " | ".join(FINDING_VI.get(item.strip(), item.strip()) for item in text.split("|"))


def vi_action(text: object) -> str:
    mapping = {
        "Package as paid lead and prepare ad test": "Đóng gói làm lead trả phí và chuẩn bị test quảng cáo",
        "Package as paid lead after manual verification": "Có thể bán lead sau khi xác minh thủ công",
        "Manually verify terms before selling": "Kiểm tra điều khoản thủ công trước khi bán",
        "Keep in watchlist": "Đưa vào danh sách theo dõi",
    }
    return mapping.get(str(text or ""), str(text or ""))


def vi_audience(text: object) -> str:
    mapping = {
        "crypto communities, trading educators, finance newsletters": "cộng đồng crypto, người dạy trading, newsletter tài chính",
        "trading educators, finance newsletters, Telegram communities": "người dạy trading, newsletter tài chính, cộng đồng Telegram",
        "deal bloggers, eCommerce creators, comparison sites, coupon communities": "blog săn deal, creator thương mại điện tử, website so sánh, cộng đồng mã giảm giá",
        "SaaS affiliates, B2B creators, software comparison sites": "affiliate SaaS, creator B2B, website so sánh phần mềm",
        "AI tool reviewers, newsletter owners, YouTube educators": "người review công cụ AI, chủ newsletter, kênh YouTube giáo dục",
    }
    return mapping.get(str(text or ""), str(text or ""))


def vi_selling_angle(text: object) -> str:
    result = str(text or "")
    replacements = {
        "lead with": "lead có",
        "recurring revenue": "hoa hồng định kỳ",
        "high": "hoa hồng cao",
        "commission": "hoa hồng",
        "flat payout": "mức trả cố định",
        "lifetime cookie": "cookie trọn đời",
        "day cookie": "ngày cookie",
        "needs affiliate program verification": "cần xác minh chương trình affiliate",
        "affiliate program found": "đã tìm thấy chương trình affiliate",
    }
    for src, dst in replacements.items():
        result = result.replace(src, dst)
    return result


def vi_reasoning(text: str) -> str:
    replacements = {
        "affiliate page found": "tìm thấy trang affiliate",
        "commission:": "hoa hồng:",
        "recurring signal": "có dấu hiệu hoa hồng định kỳ",
        "cookie:": "cookie:",
        "days": "ngày",
        "payout:": "thanh toán:",
        "category:": "ngành:",
        "activity signal found": "có tín hiệu dự án còn hoạt động",
    }
    result = text
    for src, dst in replacements.items():
        result = result.replace(src, dst)
    return result


def vi_ads_recommendation(text: object) -> str:
    mapping = {
        "Do not run Google/Bing ads until affiliate terms explicitly allow this traffic.": "Không chạy Google/Bing Ads cho đến khi điều khoản affiliate cho phép rõ ràng loại traffic này.",
        "Do not run ads until the advertiser/account has required crypto or financial certification, target market eligibility, legal disclosures, and brand approval.": "Không chạy ads cho đến khi tài khoản/nhà quảng cáo có chứng nhận crypto/tài chính cần thiết, thị trường target được phép, disclosure pháp lý và approval từ brand.",
        "Build a compliant landing page and manually verify disclosures, claims, privacy, terms, and traffic rules.": "Cần làm landing page đúng chính sách và kiểm tra thủ công disclosure, claim, privacy, terms và luật traffic.",
        "Use a value-added landing page with disclosure, original content, privacy/terms pages, and no misleading claims.": "Dùng landing page có nội dung giá trị thật, disclosure rõ, có privacy/terms và không claim gây hiểu nhầm.",
    }
    return mapping.get(str(text or ""), str(text or ""))


def send_telegram_message(token: str, chat_id: str, text: str) -> Optional[str]:
    if not token or not chat_id:
        return "Telegram chưa cấu hình."
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=20,
        )
        response.raise_for_status()
        return None
    except Exception as exc:
        return str(exc)
