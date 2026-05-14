from __future__ import annotations

import pandas as pd


NICHE_PROFILES = {
    "AI Writing": ("Stable", "High", 3.8, "Google Search, Bing Search, YouTube", "Ngách đã trưởng thành; nên thắng bằng trang review, so sánh và use-case cụ thể."),
    "AI Video": ("Rising", "High", 4.6, "Google Search, YouTube, LinkedIn", "Nhu cầu tăng từ creator, đào tạo nội bộ và marketing team."),
    "AI Voice": ("Stable", "Medium", 3.2, "Bing Search, YouTube, Reddit", "Cần viết claim cẩn thận và có disclosure rõ khi nói về giọng AI."),
    "AI SEO": ("Rising", "Medium", 3.5, "Google Search, Bing Search, Blog SEO", "Buyer intent mạnh ở keyword alternatives, comparison và review."),
    "AI Coding": ("Rising", "Medium", 4.1, "Google Search, Reddit, Developer newsletters", "Người mua cần bằng chứng kỹ thuật, tránh nội dung hype quá mức."),
    "AI Meeting": ("Rising", "Medium", 2.9, "Bing Search, LinkedIn, Google Search", "Góc productivity phù hợp nhóm khách hàng doanh nghiệp."),
    "AI Design": ("Stable", "High", 3.7, "Google Search, Pinterest, YouTube", "Nhu cầu lớn nhưng SERP đông đối thủ, nên chọn keyword ngách."),
    "CRM": ("Stable", "High", 6.5, "Google Search, LinkedIn", "Giá trị đơn hàng cao nhưng CPC đắt và chu kỳ mua dài."),
    "Productivity": ("Stable", "High", 3.1, "Google Search, Bing Search, YouTube", "Nhu cầu rộng; nên tập trung workflow cụ thể thay vì keyword quá rộng."),
    "Automation": ("Rising", "Medium", 3.4, "Google Search, Bing Search, LinkedIn", "Phù hợp góc ROI, tiết kiệm thời gian và tự động hóa workflow."),
    "Email Marketing": ("Stable", "Medium", 4.0, "Google Search, Bing Search, Blog SEO", "Có intent so sánh mạnh và thường có hoa hồng recurring."),
}


def analyze_market(offers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    niches = sorted(set(NICHE_PROFILES) | set(offers.get("niche", pd.Series(dtype=str)).dropna().astype(str)))
    for niche in niches:
        trend, competition, cpc, channels, notes = NICHE_PROFILES.get(
            niche,
            ("Stable", "Medium", 3.0, "Google Search, Bing Search", "Cần kiểm tra thị trường thủ công trước khi test."),
        )
        rows.append(
            {
                "niche": niche,
                "trend_status": trend,
                "estimated_competition": competition,
                "estimated_cpc": cpc,
                "recommended_channels": channels,
                "market_notes": notes,
            }
        )
    return pd.DataFrame(rows)
