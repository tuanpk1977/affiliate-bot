from __future__ import annotations

import pandas as pd

from config import settings


def generate_report(offer_scores: pd.DataFrame, roi_decisions: pd.DataFrame) -> str:
    top = recommended_to_test(offer_scores)
    policy = offer_scores[offer_scores["policy_notes"].astype(str).str.strip() != ""].copy()
    policy["action"] = policy.apply(
        lambda row: "Không tạo ads" if row.get("compliance_status") == "BLOCKED" else "Kiểm tra policy thật và dùng landing page review",
        axis=1,
    )
    niche = (
        offer_scores[["niche", "trend", "competition", "estimated_cpc", "market_notes"]]
        .drop_duplicates()
        .sort_values(["trend", "niche"])
    )
    campaigns = roi_decisions[roi_decisions["decision"].astype(str).isin(["PAUSE", "OPTIMIZE", "SCALE"])].copy() if not roi_decisions.empty else pd.DataFrame()

    report = "\n\n".join(
        [
            "# Báo cáo Affiliate AI",
            "## 1. Top offer nên test\n" + markdown_table(top, {
                "brand_name": "Brand",
                "niche": "Niche",
                "total_score": "Score",
                "estimated_roi": "ROI dự kiến",
                "risk_level": "Risk",
                "recommended_channels": "Kênh đề xuất",
                "test_reason": "Lý do",
            }),
            "## 2. Offer rủi ro chính sách\n" + markdown_table(policy, {
                "brand_name": "Brand",
                "policy_notes": "Vấn đề",
                "risk_level": "Mức rủi ro",
                "action": "Hành động đề xuất",
            }),
            "## 3. Niche tiềm năng\n" + markdown_table(niche, {
                "niche": "Niche",
                "trend": "Trend",
                "competition": "Competition",
                "estimated_cpc": "CPC dự kiến",
                "market_notes": "Ghi chú",
            }),
            "## 4. Campaign nên hành động\n" + markdown_table(campaigns, {
                "campaign": "Campaign",
                "ROI": "ROI",
                "profit": "Profit",
                "decision": "Quyết định",
                "decision_reason": "Lý do",
            }),
            "## 5. Việc cần làm tiếp theo\n"
            "- Kiểm tra affiliate policy thật.\n"
            "- Tạo landing page review.\n"
            "- Upload CSV thủ công lên Ads Editor.\n"
            "- Test ngân sách nhỏ.\n"
            "- Theo dõi ROI sau 3-5 ngày.",
            "## 6. Việc cần xác minh trước khi chạy ads thật\n"
            "- Đã kiểm tra affiliate terms chưa?\n"
            "- Đã kiểm tra trademark bidding chưa?\n"
            "- Đã kiểm tra direct linking chưa?\n"
            "- Đã kiểm tra payout thật chưa?\n"
            "- Đã kiểm tra cookie duration thật chưa?\n"
            "- Đã thay Final URL local bằng URL landing page thật trên domain của bạn chưa?",
        ]
    )
    settings.reports_file.write_text(report, encoding="utf-8")
    return report


def recommended_to_test(df: pd.DataFrame) -> pd.DataFrame:
    top = df[
        (pd.to_numeric(df["total_score"], errors="coerce") >= 80)
        & (df["risk_level"].isin(["Low", "Medium"]))
        & (pd.to_numeric(df["estimated_roi"], errors="coerce") > 0)
        & (df["compliance_status"] != "BLOCKED")
        & (df["competition"].isin(["Low", "Medium"]))
    ].sort_values(["total_score", "estimated_roi"], ascending=False).head(8).copy()
    if not top.empty:
        top["test_reason"] = top.apply(build_test_reason, axis=1)
    return top


def build_test_reason(row: pd.Series) -> str:
    reasons = []
    if float(row.get("total_score") or 0) >= 80:
        reasons.append("điểm cao")
    if str(row.get("buyer_intent_label", "")) == "High":
        reasons.append("buyer intent cao")
    if str(row.get("competition", "")) in {"Low", "Medium"}:
        reasons.append("cạnh tranh chưa quá cao")
    if float(row.get("estimated_roi") or 0) > 0:
        reasons.append("ROI dự kiến dương")
    return ", ".join(reasons)


def markdown_table(df: pd.DataFrame, columns: dict[str, str]) -> str:
    available = [column for column in columns if column in df.columns]
    if df.empty or not available:
        return "Chưa có dữ liệu."
    display = df[available].rename(columns=columns).astype(str)
    headers = list(display.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in display.iterrows():
        values = [str(row.get(header, "")).replace("|", "/") for header in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
