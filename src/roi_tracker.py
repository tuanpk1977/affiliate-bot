from __future__ import annotations

import pandas as pd

ROI_INPUT = "data/input/ad_results.csv"
ROI_OUTPUT = "data/output/roi_report.csv"
ROI_SUMMARY = "data/output/roi_summary.txt"


def build_roi_report() -> pd.DataFrame:
    df = load_roi_input()
    if df.empty:
        empty = pd.DataFrame(
            columns=[
                "campaign",
                "cost",
                "clicks",
                "conversions",
                "revenue",
                "cpc",
                "cpa",
                "profit",
                "roi_percent",
                "decision",
                "reason",
            ]
        )
        empty.to_csv(ROI_OUTPUT, index=False)
        write_summary(empty)
        return empty

    rows = []
    for _, row in df.iterrows():
        campaign = str(row.get("campaign", "")).strip()
        cost = to_float(row.get("cost", 0))
        clicks = to_float(row.get("clicks", 0))
        conversions = to_float(row.get("conversions", 0))
        revenue = to_float(row.get("revenue", 0))
        cpc = cost / clicks if clicks else 0
        cpa = cost / conversions if conversions else 0
        profit = revenue - cost
        roi_percent = (profit / cost * 100) if cost else 0
        decision, reason = decide_campaign(
            cost=cost,
            clicks=clicks,
            conversions=conversions,
            revenue=revenue,
            profit=profit,
            roi_percent=roi_percent,
        )
        rows.append(
            {
                "campaign": campaign,
                "cost": round(cost, 2),
                "clicks": int(clicks),
                "conversions": int(conversions),
                "revenue": round(revenue, 2),
                "cpc": round(cpc, 2),
                "cpa": round(cpa, 2),
                "profit": round(profit, 2),
                "roi_percent": round(roi_percent, 2),
                "decision": decision,
                "reason": reason,
            }
        )

    result = pd.DataFrame(rows).sort_values(["roi_percent", "profit"], ascending=[False, False])
    result.to_csv(ROI_OUTPUT, index=False)
    write_summary(result)
    return result


def load_roi_input() -> pd.DataFrame:
    try:
        return pd.read_csv(ROI_INPUT)
    except FileNotFoundError:
        return pd.DataFrame()


def decide_campaign(
    cost: float,
    clicks: float,
    conversions: float,
    revenue: float,
    profit: float,
    roi_percent: float,
) -> tuple[str, str]:
    if cost == 0 and clicks == 0:
        return "no_data", "Chưa có dữ liệu để đánh giá."
    if clicks < 30 and conversions == 0:
        return "keep_testing", "Chưa đủ click để kết luận."
    if cost >= 20 and conversions == 0:
        return "pause", "Đã tiêu ngân sách nhưng chưa có conversion."
    if profit < 0 and cost >= 20:
        return "pause", "Campaign đang lỗ và đã đủ dữ liệu tối thiểu."
    if roi_percent >= 50 and conversions >= 2:
        return "scale", "ROI tốt, có thể tăng ngân sách từ từ."
    if roi_percent > 0:
        return "keep", "Đang có lời nhưng cần thêm dữ liệu trước khi scale."
    return "watch", "Chưa rõ lời/lỗ, tiếp tục theo dõi với ngân sách nhỏ."


def write_summary(df: pd.DataFrame) -> None:
    lines = ["TÓM TẮT ROI ADS", ""]
    if df.empty:
        lines.extend(
            [
                "Chưa có dữ liệu ROI.",
                "Hãy điền hoặc export dữ liệu vào data/input/ad_results.csv rồi chạy lại bot.",
            ]
        )
    else:
        for _, row in df.iterrows():
            lines.append(
                f"- {row.get('campaign', '')}: {vi_decision(row.get('decision', ''))} | "
                f"ROI {row.get('roi_percent', '')}% | Profit {row.get('profit', '')} | "
                f"Lý do: {row.get('reason', '')}"
            )
    with open(ROI_SUMMARY, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))


def vi_decision(decision: object) -> str:
    mapping = {
        "no_data": "Chưa có dữ liệu",
        "keep_testing": "Tiếp tục test",
        "pause": "Tắt campaign",
        "scale": "Tăng ngân sách",
        "keep": "Giữ campaign",
        "watch": "Theo dõi thêm",
    }
    return mapping.get(str(decision or ""), str(decision or ""))


def to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
