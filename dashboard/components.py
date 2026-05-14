from __future__ import annotations

import html

import pandas as pd
import streamlit as st


RISK_LABELS = {"Low": "Thấp", "Medium": "Trung bình", "High": "Cao"}
TREND_LABELS = {"Rising": "Đang tăng", "Stable": "Ổn định", "Declining": "Giảm"}
COMPETITION_LABELS = {"Low": "Thấp", "Medium": "Trung bình", "High": "Cao"}
INTENT_LABELS = {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp"}


def metric_cards(offer_scores: pd.DataFrame) -> None:
    total = len(offer_scores)
    avg = round(float(offer_scores["total_score"].mean()), 1) if total and "total_score" in offer_scores else 0
    safe = int((offer_scores["compliance_status"] == "SAFE").sum()) if total and "compliance_status" in offer_scores else 0
    blocked = int((offer_scores["compliance_status"] == "BLOCKED").sum()) if total and "compliance_status" in offer_scores else 0
    best_roi = round(float(offer_scores["estimated_roi"].max()), 1) if total and "estimated_roi" in offer_scores else 0
    cols = st.columns(5)
    cols[0].metric("Tổng số offer", total)
    cols[1].metric("Điểm trung bình", avg)
    cols[2].metric("Offer an toàn", safe)
    cols[3].metric("Offer bị chặn", blocked)
    cols[4].metric("ROI tốt nhất", f"{best_roi}%")


def inject_dashboard_css() -> None:
    st.markdown(
        """
        <style>
        .aiip-card {
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            padding: 14px 16px;
            background: #ffffff;
            min-height: 232px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
        }
        .aiip-card h3 {
            margin: 0 0 4px 0;
            font-size: 18px;
            letter-spacing: 0;
        }
        .aiip-muted {
            color: #64748b;
            font-size: 13px;
            margin-bottom: 10px;
        }
        .aiip-score {
            font-size: 28px;
            font-weight: 700;
            color: #0f766e;
            margin: 8px 0;
        }
        .aiip-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 6px 10px;
            font-size: 13px;
            margin: 10px 0;
        }
        .aiip-label {
            color: #64748b;
        }
        .aiip-rec {
            border-top: 1px solid #e2e8f0;
            margin-top: 10px;
            padding-top: 10px;
            color: #334155;
            font-size: 13px;
        }
        .aiip-pill {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 999px;
            background: #ecfdf5;
            color: #047857;
            font-size: 12px;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def offer_card(row: pd.Series, test_first: bool = False) -> None:
    score = row.get("total_score", "")
    recommendation = short_text(str(row.get("recommendation", "")), 110)
    extra = ""
    if test_first:
        extra = f"""
            <div class="aiip-rec">
                <strong>Lý do nên test:</strong> {html.escape(test_reason(row))}<br>
                <strong>Kênh nên chạy:</strong> {html.escape(str(row.get('recommended_channels', '')))}<br>
                <strong>Ngân sách test:</strong> {html.escape(suggest_budget(row))}<br>
                <strong>Cảnh báo:</strong> {html.escape(policy_warning(row))}
            </div>
        """
    else:
        extra = f'<div class="aiip-rec">{html.escape(recommendation)}</div>'

    st.markdown(
        f"""
        <div class="aiip-card">
            <h3>{html.escape(str(row.get('brand_name', '')))}</h3>
            <div class="aiip-muted">{html.escape(str(row.get('niche', '')))} · {html.escape(str(row.get('recommended_channels', '')))}</div>
            <div class="aiip-score">{score}/100 <span style="font-size:14px;color:#475569">Xếp hạng {html.escape(str(row.get('grade', '')))}</span></div>
            <div class="aiip-grid">
                <div><span class="aiip-label">Rủi ro</span><br>{risk_label(row.get('risk_level', ''))}</div>
                <div><span class="aiip-label">Xu hướng</span><br>{trend_label(row.get('trend', ''))}</div>
                <div><span class="aiip-label">Cạnh tranh</span><br>{competition_label(row.get('competition', ''))}</div>
                <div><span class="aiip-label">Buyer Intent</span><br>{intent_label(row.get('buyer_intent_label', ''))}</div>
                <div><span class="aiip-label">ROI dự kiến</span><br>{row.get('estimated_roi', '')}%</div>
                <div><span class="aiip-label">Chính sách</span><br>{html.escape(str(row.get('compliance_status', '')))}</div>
            </div>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(value: str) -> str:
    color = "#15803d" if value in {"SAFE", "SCALE", "TEST_FIRST"} else "#b45309" if value in {"WARNING", "WATCH", "OPTIMIZE", "VERIFY_THEN_TEST"} else "#b91c1c"
    return f"<span style='color:white;background:{color};padding:3px 8px;border-radius:6px;font-size:12px'>{html.escape(value)}</span>"


def read_csv(path) -> pd.DataFrame:
    try:
        return pd.read_csv(path).fillna("")
    except Exception:
        return pd.DataFrame()


def rename_for_display(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    available = [column for column in columns if column in df.columns]
    if not available:
        return pd.DataFrame()
    return df[available].rename(columns=columns)


def risk_label(value: object) -> str:
    return RISK_LABELS.get(str(value), str(value))


def trend_label(value: object) -> str:
    return TREND_LABELS.get(str(value), str(value))


def competition_label(value: object) -> str:
    return COMPETITION_LABELS.get(str(value), str(value))


def intent_label(value: object) -> str:
    return INTENT_LABELS.get(str(value), str(value))


def short_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "."


def test_reason(row: pd.Series) -> str:
    reasons = []
    if float(row.get("total_score") or 0) >= 80:
        reasons.append("điểm tổng cao")
    if str(row.get("buyer_intent_label", "")) == "High":
        reasons.append("buyer intent cao")
    if str(row.get("competition", "")) in {"Low", "Medium"}:
        reasons.append("cạnh tranh chưa quá cao")
    if float(row.get("estimated_roi") or 0) > 0:
        reasons.append("ROI dự kiến dương")
    return ", ".join(reasons) or "cần kiểm tra thêm trước khi test"


def suggest_budget(row: pd.Series) -> str:
    cpc = float(row.get("estimated_cpc") or 3)
    if cpc >= 5:
        return "10-20 USD/ngày, chỉ dùng keyword rất hẹp"
    return "10-25 USD/ngày trong 3-5 ngày"


def policy_warning(row: pd.Series) -> str:
    notes = str(row.get("policy_notes", "")).strip()
    return notes if notes else "Kiểm tra affiliate policy thật trước khi upload CSV."
