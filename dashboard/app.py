from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from dashboard.components import (
    competition_label,
    inject_dashboard_css,
    metric_cards,
    offer_card,
    read_csv,
    rename_for_display,
    risk_label,
    status_badge,
    test_reason,
    trend_label,
)
from main import main as run_pipeline
from modules.affiliate_links import load_affiliate_links, save_affiliate_links, upsert_affiliate_link
from modules.affiliate_tracking import CLICK_EVENT_COLUMNS, append_click_event, load_click_events
from modules.affiliate_skills import list_skills, run_skill, save_draft
from modules.auto_offer_importer import (
    build_offer_record,
    load_user_offers,
    save_many_from_links,
    save_user_offer,
    validate_required_fields,
)
from modules import content_approval as content_approval_module
from modules.action_priority import (
    generate_article_draft as generate_action_article_draft,
    generate_internal_link_plan as generate_action_internal_link_plan,
    generate_social_pack as generate_action_social_pack,
    mark_action_status,
)
from modules.distribution_boost import save_distribution_boost
from modules.profit_simulator import simulate_offer_profit, simulate_scenarios
from modules.post_deploy_kit import (
    CHECKLIST_ITEMS,
    build_indexing_priority,
    build_social_posting_queue,
    go_page_count,
    load_click_tracking_report,
    load_post_deploy_checklist,
    run_post_deploy_kit,
    save_post_deploy_checklist,
)
from modules.site_builder import build_site_output
from modules.social_content_generator import (
    generate_social_pack,
    load_social_accounts,
    read_social_post_report,
    write_distribution_summary,
)
from modules.social_distribution import (
    VALID_STATUSES as SOCIAL_REVIEW_STATUSES,
    X_THREAD_MODES,
    build_x_thread_preview,
    content_angle_dataframe,
    ensure_social_distribution_assets,
    generate_deep_dive_outline,
    generate_more_variations,
    load_content_angle_history,
    load_social_limits,
    load_publish_modes,
    load_social_calendar,
    posted_today_count,
    save_social_calendar,
    save_publish_modes,
    social_asset_path,
    telegram_config_status,
    update_calendar_status,
)
from modules.social_draft_generator import (
    REQUIRED_DRAFT_FIELDS,
    load_all_social_drafts,
    move_draft_status,
    save_draft_record,
)
from modules.social_scheduler import schedule_approved_posts
from modules.social_publish_queue import (
    clear_duplicate_scheduled_posts,
    enqueue_posts,
    load_queue,
    load_social_schedule,
    process_due_queue,
    remove_queue_items,
    save_queue,
    save_social_schedule,
)
from modules.topic_expansion import generate_topic_draft, topic_dataframe

VALID_STATUSES = getattr(content_approval_module, "VALID_STATUSES", ["Draft", "Pending Review", "Need Edit", "Approved", "Rejected", "Published"])
can_approve = getattr(content_approval_module, "can_approve")
create_draft = getattr(content_approval_module, "create_draft")
export_html = getattr(content_approval_module, "export_html")
export_markdown = getattr(content_approval_module, "export_markdown")
generate_aeo_ideas = getattr(content_approval_module, "generate_aeo_ideas")
generate_draft_content = getattr(content_approval_module, "generate_draft_content")
generate_multichannel_pack = getattr(content_approval_module, "generate_multichannel_pack")
generate_offpage_pack = getattr(content_approval_module, "generate_offpage_pack")
publish_static_draft = getattr(content_approval_module, "publish_static_draft", getattr(content_approval_module, "publish_static_page", None))
draft_slugify = getattr(content_approval_module, "slugify")
update_draft = getattr(content_approval_module, "update_draft")
if publish_static_draft is None:
    def publish_static_draft(*args: object, **kwargs: object) -> tuple[bool, str]:
        return False, "Thiếu hàm publish static page trong modules.content_approval."


def fix_mojibake_text(value: object) -> str:
    """Repair common Windows mojibake already stored in old CSV/text rows."""
    text = "" if value is None else str(value)
    if not text:
        return text
    try:
        raw = bytearray()
        for ch in text:
            code = ord(ch)
            if 0x80 <= code <= 0x9F:
                raw.append(code)
            else:
                raw.extend(ch.encode("cp1252"))
        fixed = raw.decode("utf-8")
    except Exception:
        return text
    return fixed if fixed != text else text


def fix_mojibake_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    fixed = df.copy()
    for column in fixed.select_dtypes(include=["object"]).columns:
        fixed[column] = fixed[column].map(fix_mojibake_text)
    return fixed


_read_csv_base = read_csv


def read_csv(path) -> pd.DataFrame:  # type: ignore[no-redef]
    return fix_mojibake_df(_read_csv_base(path))


def load_review_queue() -> pd.DataFrame:
    loader = getattr(content_approval_module, "load_review_queue", None)
    if callable(loader):
        return loader()
    importer = getattr(content_approval_module, "import_affiliate_os_drafts", None)
    if callable(importer):
        importer()
    fallback_loader = getattr(content_approval_module, "load_drafts", None)
    if callable(fallback_loader):
        return fallback_loader()
    return pd.DataFrame()


def read_generated_social_posts_from_files() -> pd.DataFrame:
    report = read_social_post_report()
    rows = report.to_dict("records") if not report.empty else []
    known_paths = {str(row.get("output_path", "")) for row in rows}
    root = settings.base_dir / "draft_output" / "social_posts"
    if root.exists():
        for path in sorted(root.glob("*/*.txt")):
            if str(path) in known_paths:
                continue
            rows.append(
                {
                    "post_id": f"{path.parent.name}-{path.stem}",
                    "draft_id": "",
                    "article_slug": path.parent.name,
                    "platform": path.stem,
                    "title": path.parent.name.replace("-", " ").title(),
                    "article_url": f"{(settings.base_site_url or settings.site_domain or 'https://review.mssmileenglish.com').rstrip('/')}/{path.parent.name}/",
                    "status": "Pending Review",
                    "output_path": str(path),
                    "created_at": "",
                    "scheduled_time": "",
                    "published_at": "",
                    "error": "",
                    "image_path": str(settings.base_dir / "draft_output" / "social_images" / f"{path.parent.name}.png"),
                }
            )
    return pd.DataFrame(rows).fillna("")


def render_social_automation_approval_queue() -> None:
    st.markdown("### Social Automation Approval Queue")
    st.caption("Draft -> approve/reject/edit -> schedule. This is local-only and never posts automatically.")
    records = load_all_social_drafts()
    if not records:
        st.info("No social automation drafts yet. Run `python scripts/generate_social_drafts.py` to create draft posts.")
        return
    df = pd.DataFrame(records).fillna("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Drafts", int((df["status"].astype(str) == "draft").sum()))
    c2.metric("Approved", int((df["status"].astype(str) == "approved").sum()))
    c3.metric("Rejected", int((df["status"].astype(str) == "rejected").sum()))
    c4.metric("Scheduled", int((df["status"].astype(str) == "scheduled").sum()))

    f1, f2, f3 = st.columns(3)
    platform_filter = f1.selectbox("Automation platform", ["All"] + sorted(df["platform"].astype(str).unique().tolist()), key="automation_platform_filter")
    language_filter = f2.selectbox("Language", ["All"] + sorted(df["language"].astype(str).unique().tolist()), key="automation_language_filter")
    status_filter = f3.selectbox("Automation status", ["All", "draft", "approved", "rejected", "scheduled", "posted"], key="automation_status_filter")
    view = df.copy()
    if platform_filter != "All":
        view = view[view["platform"].astype(str) == platform_filter]
    if language_filter != "All":
        view = view[view["language"].astype(str) == language_filter]
    if status_filter != "All":
        view = view[view["status"].astype(str) == status_filter]
    show_cols = ["id", "platform", "language", "title", "source_url", "cta_url", "status", "created_at", "approved_at", "scheduled_at"]
    st.dataframe(view[[col for col in show_cols if col in view.columns]], use_container_width=True, hide_index=True)
    if view.empty:
        return

    options = {
        f"{row.get('platform', '')} | {row.get('language', '')} | {row.get('title', '')} | {row.get('id', '')}": row.get("id", "")
        for row in view.to_dict("records")
    }
    selected_label = st.selectbox("Select social draft", list(options.keys()), key="automation_selected_draft")
    selected_id = str(options[selected_label])
    selected = df[df["id"].astype(str) == selected_id].iloc[0].to_dict()
    st.markdown(f"#### {selected.get('title', '')}")
    st.caption(f"Platform: {selected.get('platform', '')} | Language: {selected.get('language', '')} | Status: {selected.get('status', '')}")
    st.text_input("Source URL", value=str(selected.get("source_url", "")), disabled=True, key=f"automation_source_{selected_id}")
    st.text_input("CTA URL", value=str(selected.get("cta_url", "")), disabled=True, key=f"automation_cta_{selected_id}")
    edited_content = st.text_area("Content", value=str(selected.get("content", "")), height=260, key=f"automation_content_{selected_id}")
    edit_col, approve_col, reject_col, schedule_col = st.columns(4)
    if edit_col.button("Edit / Save", key=f"automation_edit_{selected_id}"):
        updated = {field: str(selected.get(field, "")) for field in REQUIRED_DRAFT_FIELDS}
        updated.update(selected)
        updated["content"] = edited_content
        status_dir_map = {
            "draft": "drafts",
            "approved": "approved",
            "rejected": "rejected",
            "scheduled": "scheduled",
            "posted": "posted",
        }
        save_draft_record(updated, status_dir_map.get(str(selected.get("status", "draft")), "drafts"), overwrite=True)
        st.success("Saved draft content locally.")
        st.rerun()
    if approve_col.button("Approve", key=f"automation_approve_{selected_id}"):
        move_draft_status(selected_id, "approved", {"content": edited_content})
        st.success("Approved. It can now be scheduled.")
        st.rerun()
    if reject_col.button("Reject", key=f"automation_reject_{selected_id}"):
        move_draft_status(selected_id, "rejected", {"content": edited_content})
        st.success("Rejected and moved to social_assets/rejected.")
        st.rerun()
    if schedule_col.button("Schedule approved", key=f"automation_schedule_{selected_id}"):
        scheduled = schedule_approved_posts()
        st.success(f"Scheduled {len(scheduled)} approved draft(s).")
        st.rerun()


def render_social_distribution_page(review_queue: pd.DataFrame) -> None:
    st.header("Social Distribution")
    st.warning("Local-safe mode: no auto-posting before approval. Facebook, LinkedIn and X/Twitter are copy-ready only.")

    social_posts_df = read_generated_social_posts_from_files()
    queue_df = load_queue()
    accounts = load_social_accounts()
    telegram_cfg = accounts.get("telegram", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Generated posts", len(social_posts_df))
    c2.metric("Queue items", len(queue_df))
    c3.metric("Scheduled", int((queue_df["status"].astype(str) == "Scheduled").sum()) if not queue_df.empty and "status" in queue_df.columns else 0)
    c4.metric("Published", int((queue_df["status"].astype(str) == "Published").sum()) if not queue_df.empty and "status" in queue_df.columns else 0)

    st.markdown("### AI coding topic expansion")
    topics_df = topic_dataframe()
    if topics_df.empty:
        st.info("No topic config found.")
    else:
        t1, t2 = st.columns([1, 2])
        group_options = ["All"] + sorted(topics_df["group"].astype(str).unique().tolist())
        selected_group = t1.selectbox("Topic group", group_options, key="social_topic_group")
        topic_view = topics_df if selected_group == "All" else topics_df[topics_df["group"].astype(str) == selected_group]
        t2.dataframe(topic_view, use_container_width=True, hide_index=True)
        selected_topic_slug = st.selectbox("Choose topic to create draft", topic_view["slug"].astype(str).tolist(), key="social_topic_slug")
        selected_topic = topic_view[topic_view["slug"].astype(str) == selected_topic_slug].iloc[0].to_dict()
        st.caption("Draft only: topic pages go to the approval queue first. They are not added to sitemap or indexes until approved/published.")
        if st.button("Generate topic draft", key="social_generate_topic_draft"):
            record = generate_topic_draft(selected_topic)
            st.success(f"Created draft {record['draft_id']} for {record['title']}. Review it in Content Approval.")
            review_queue = load_review_queue()

    st.markdown("### Social account config")
    st.write(f"Telegram enabled: {telegram_cfg.get('enabled', False)} | token set: {bool(telegram_cfg.get('bot_token'))} | chat_id set: {bool(telegram_cfg.get('chat_id'))}")
    st.caption("Use `.env` for secrets: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Do not hardcode tokens.")

    st.markdown("### Schedule settings")
    schedule = load_social_schedule()
    edited_schedule = {}
    schedule_cols = st.columns(4)
    for index, platform in enumerate(["telegram", "facebook", "linkedin", "twitter"]):
        config = schedule.get(platform, {})
        with schedule_cols[index]:
            st.markdown(f"**{platform.title() if platform != 'twitter' else 'Twitter/X'}**")
            enabled = st.checkbox("Enabled", value=bool(config.get("enabled", False)), key=f"schedule_enabled_{platform}")
            times_text = st.text_input(
                "Daily times",
                value=", ".join(config.get("daily_times", [])),
                key=f"schedule_times_{platform}",
                help="Use HH:MM comma-separated, e.g. 09:00, 20:00",
            )
            max_posts = st.number_input(
                "Max posts/day",
                min_value=1,
                max_value=24,
                value=int(config.get("max_posts_per_day", 1) or 1),
                step=1,
                key=f"schedule_max_{platform}",
            )
            edited_schedule[platform] = {
                "enabled": enabled,
                "daily_times": [item.strip() for item in times_text.split(",") if item.strip()],
                "max_posts_per_day": int(max_posts),
            }
    if st.button("Save schedule settings", key="save_social_schedule"):
        save_social_schedule(edited_schedule)
        st.success("Saved config/social_schedule.json")

    approved_articles = review_queue[review_queue["status"].astype(str) == "Published"] if not review_queue.empty else pd.DataFrame()
    st.markdown("### Published articles")
    if approved_articles.empty:
        st.info("No Published article is available yet. Approve a draft, then use Publish to Site before generating social posts.")
        st.dataframe(pd.DataFrame(columns=["draft_id", "title", "status", "slug"]), use_container_width=True, hide_index=True)
        return

    st.dataframe(approved_articles[["draft_id", "title", "status", "slug", "content_type"]], use_container_width=True, hide_index=True)
    article_id = st.selectbox("Choose article", approved_articles["draft_id"].astype(str).tolist(), key="sidebar_social_article_id")
    article = approved_articles[approved_articles["draft_id"].astype(str) == article_id].iloc[0].to_dict()
    slug = draft_slugify(article.get("slug") or article.get("title") or article_id)
    st.write(f"Selected: **{article.get('title', '')}**")
    image_preview_path = settings.base_dir / "draft_output" / "social_images" / f"{slug}.png"
    if image_preview_path.exists():
        st.image(str(image_preview_path), caption="Social thumbnail preview", use_container_width=True)

    p1, p2, p3, p4 = st.columns(4)
    selected_platforms = []
    if p1.checkbox("Facebook", value=True, key="sidebar_social_fb"):
        selected_platforms.append("facebook")
    if p2.checkbox("Telegram", value=True, key="sidebar_social_tg"):
        selected_platforms.append("telegram")
    if p3.checkbox("LinkedIn", value=True, key="sidebar_social_li"):
        selected_platforms.append("linkedin")
    if p4.checkbox("Twitter/X", value=True, key="sidebar_social_tw"):
        selected_platforms.append("twitter")

    if st.button("Generate social variations", key="sidebar_generate_social"):
        if str(article.get("status", "")) != "Published" or not str(article.get("target_url", "")).strip():
            st.error("Publish to Site first so social posts use a real live URL.")
            return
        records = generate_social_pack(article, selected_platforms)
        boost_path = save_distribution_boost(slug, str(article.get("title", "")), str(article.get("target_url", "")), str(article.get("draft_content", "")))
        st.success(f"Generated {len(records)} social posts. Boost file: {boost_path}")
        social_posts_df = read_generated_social_posts_from_files()
        image_preview_path = settings.base_dir / "draft_output" / "social_images" / f"{slug}.png"
        if image_preview_path.exists():
            st.image(str(image_preview_path), caption="Generated social thumbnail", use_container_width=True)

    st.markdown("### Social previews")
    current_social = social_posts_df[social_posts_df["article_slug"].astype(str) == slug] if not social_posts_df.empty and "article_slug" in social_posts_df.columns else pd.DataFrame()
    preview_cols = st.columns(4)
    for idx, platform in enumerate(["facebook", "telegram", "linkedin", "twitter"]):
        with preview_cols[idx]:
            st.markdown(f"**{platform.title() if platform != 'twitter' else 'Twitter/X'} preview**")
            match = current_social[current_social["platform"].astype(str) == platform] if not current_social.empty else pd.DataFrame()
            if match.empty:
                st.info("Not generated yet.")
                continue
            output_path = Path(str(match.iloc[0].get("output_path", "")))
            preview = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
            image_path = Path(str(match.iloc[0].get("image_path", "")))
            if image_path.exists():
                st.image(str(image_path), caption=f"{platform} thumbnail", use_container_width=True)
            st.text_area(f"{platform} content", value=preview, height=260, disabled=True, key=f"social_preview_{platform}_{slug}")

    st.markdown("### Add to queue")
    if current_social.empty:
        st.info("Generate social variations first.")
    else:
        st.dataframe(current_social[["post_id", "platform", "status", "output_path", "article_url"]], use_container_width=True, hide_index=True)
        selection_version = int(st.session_state.get("sidebar_queue_selection_version", 0))
        queue_options = current_social["post_id"].astype(str).tolist()
        queue_default = [item for item in st.session_state.get("sidebar_social_posts_to_queue_value", []) if item in queue_options]
        selected_post_ids = st.multiselect(
            "Bài viết cần xếp hàng chờ",
            queue_options,
            default=queue_default,
            key=f"sidebar_social_posts_to_queue_{selection_version}",
        )
        st.session_state["sidebar_social_posts_to_queue_value"] = selected_post_ids
        if st.button("Clear Pending Selection", key="sidebar_clear_pending_selection"):
            st.session_state["sidebar_social_posts_to_queue_value"] = []
            st.session_state["sidebar_queue_selection_version"] = selection_version + 1
            st.rerun()
        schedule_time = st.text_input("Manual schedule start ISO (optional)", value="", key="sidebar_social_schedule")
        st.caption("Leave this empty to use config/social_schedule.json daily_times automatically.")
        random_delay = st.number_input("Random delay minutes", min_value=0, max_value=240, value=0, step=5, key="sidebar_social_delay")
        if st.button("Add selected posts to queue", key="sidebar_social_enqueue"):
            before = len(load_queue())
            queue_df = enqueue_posts(selected_post_ids, selected_platforms, schedule_time, int(random_delay))
            queue_df = save_queue(queue_df)
            write_distribution_summary(queue_df)
            added = max(0, len(queue_df) - before)
            skipped = max(0, len(selected_post_ids) - added)
            st.success(f"Queued {added} posts. Skipped {skipped} duplicates. Nothing is posted automatically.")
            st.session_state["sidebar_social_posts_to_queue_value"] = []
            st.session_state["sidebar_queue_selection_version"] = selection_version + 1
            st.rerun()

    st.markdown("### Queue status")
    queue_df = load_queue()
    if st.button("Clear duplicate scheduled posts", key="clear_duplicate_scheduled_posts"):
        queue_df, removed = clear_duplicate_scheduled_posts()
        write_distribution_summary(queue_df)
        st.success(f"Removed {removed} duplicate scheduled rows.")
        st.rerun()
    if not queue_df.empty:
        removable = queue_df["queue_id"].astype(str).tolist()
        remove_ids = st.multiselect("Remove queued items permanently", removable, key="sidebar_remove_queue_items")
        if st.button("Remove selected queued items", key="sidebar_remove_queue_button"):
            queue_df, removed = remove_queue_items(remove_ids)
            write_distribution_summary(queue_df)
            st.success(f"Removed {removed} queued rows and saved data/social_publish_queue.csv.")
            st.rerun()
    st.dataframe(queue_df, use_container_width=True, hide_index=True)


def render_manual_social_distribution_page() -> None:
    st.header("Phân phối xã hội")
    st.warning("Local-safe: chỉ tạo nội dung và cập nhật CSV. Không auto-post, không gọi API ngoài, không deploy.")
    with st.expander("Social Automation With Human Approval", expanded=True):
        render_social_automation_approval_queue()
    calendar = ensure_social_distribution_assets()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng bài seed", len(calendar))
    c2.metric("Chờ duyệt", int((calendar["status"].astype(str) == "Pending Review").sum()) if not calendar.empty else 0)
    c3.metric("Approved", int((calendar["status"].astype(str) == "Approved").sum()) if not calendar.empty else 0)
    c4.metric("Ready/Posted", int(calendar["status"].astype(str).isin(["Ready to Post", "Posted"]).sum()) if not calendar.empty else 0)
    stat_cols = st.columns(4)
    total_approved = int(calendar["status"].astype(str).isin(["Approved", "Scheduled", "Ready to Post", "Posted"]).sum()) if not calendar.empty else 0
    total_auto_posted = int(((calendar["platform"].astype(str).str.lower() == "telegram") & (calendar["status"].astype(str) == "Posted")).sum()) if not calendar.empty else 0
    total_manual = int((calendar["status"].astype(str) == "Ready to Post").sum()) if not calendar.empty else 0
    stat_cols[0].metric("Total approved", total_approved)
    stat_cols[1].metric("Total auto-posted", total_auto_posted)
    stat_cols[2].metric("Total manual", total_manual)
    stat_cols[3].metric("CTR", "chưa có data")
    if not calendar.empty:
        with st.expander("Platform breakdown", expanded=False):
            breakdown = calendar.groupby(["platform", "status"]).size().reset_index(name="count")
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

    telegram_ready, telegram_message = telegram_config_status()
    if telegram_ready:
        st.success(telegram_message)
    else:
        st.warning(telegram_message)

    st.markdown("### Publish Mode")
    modes = load_publish_modes()
    limits = load_social_limits()
    mode_updates: dict[str, str] = {}
    mode_cols = st.columns(4)
    platform_labels = [
        ("telegram", "Telegram"),
        ("facebook", "Facebook"),
        ("linkedin", "LinkedIn"),
        ("twitter", "Twitter/X"),
    ]
    for idx, (key, label) in enumerate(platform_labels):
        with mode_cols[idx]:
            current = modes.get(key, "manual")
            selected = st.selectbox(
                label,
                ["manual", "auto"],
                index=0 if current == "manual" else 1,
                key=f"publish_mode_{key}",
            )
            mode_updates[key] = selected
            if key != "telegram" and selected == "auto":
                st.warning("Auto-post for this platform is not enabled yet. Manual copy-ready mode is safer.")
            if key == "telegram" and selected == "auto" and not telegram_ready:
                st.warning("Telegram Auto cần token/chat_id trước khi scheduler có thể gửi.")
    if st.button("Save publish modes", key="save_social_publish_modes"):
        save_publish_modes(mode_updates)
        st.success("Saved config/social_publish_mode.json")
        st.rerun()

    st.markdown("### Daily limits")
    limit_rows = []
    for key, label in platform_labels:
        config = limits.get(key, {})
        limit_rows.append(
            {
                "platform": label,
                "mode": modes.get(key, "manual"),
                "daily_limit": config.get("daily_limit", ""),
                "cooldown_minutes": config.get("cooldown_minutes", ""),
                "posted_or_ready_today": posted_today_count(calendar, key),
            }
        )
    st.dataframe(pd.DataFrame(limit_rows), use_container_width=True, hide_index=True)

    st.markdown("### Content Expansion Engine")
    st.caption("Tạo nhiều góc khai thác cho cùng một topic để tránh lặp hook, opening và CTA. Mỗi variation vẫn chờ duyệt trước khi đăng.")
    angles_df = content_angle_dataframe()
    history_df = load_content_angle_history()
    if angles_df.empty:
        st.info("Chưa có topic angle config.")
    else:
        h1, h2, h3 = st.columns(3)
        h1.metric("Topics", int(angles_df["topic_slug"].nunique()))
        h2.metric("Angles/topic", int(angles_df["angle"].nunique()))
        h3.metric("Generated history", len(history_df))
        topic_options = angles_df[["topic", "topic_slug"]].drop_duplicates().sort_values("topic")
        topic_label_map = {
            f"{row.topic} | {row.topic_slug}": row.topic_slug
            for row in topic_options.itertuples(index=False)
        }
        selected_topic_label = st.selectbox("Topic", list(topic_label_map.keys()), key="angle_topic_select")
        selected_topic_slug = topic_label_map[selected_topic_label]
        topic_angles = angles_df[angles_df["topic_slug"].astype(str) == selected_topic_slug].copy()
        angle_label_map = {
            f"{row.angle} | {row.content_style}": row.angle
            for row in topic_angles.itertuples(index=False)
        }
        selected_angle_label = st.selectbox("Angle", list(angle_label_map.keys()), key="angle_select")
        selected_angle = angle_label_map[selected_angle_label]
        selected_meta = topic_angles[topic_angles["angle"].astype(str) == selected_angle].iloc[0].to_dict()
        st.markdown(
            f"**Hook:** {selected_meta.get('hook', '')}  \n"
            f"**Summary:** {selected_meta.get('summary', '')}  \n"
            f"**CTA:** {selected_meta.get('cta', '')}  \n"
            f"**Suggested styles:** {selected_meta.get('suggested_social_styles', '')}"
        )
        if st.button("Generate More Variations", key="generate_more_social_variations"):
            created = generate_more_variations(selected_topic_slug, selected_angle)
            st.success(f"Đã tạo {len(created)} variations: 3 X/Twitter, 2 LinkedIn, 2 Telegram, 2 Facebook. Tất cả đang ở Pending Review.")
            st.rerun()
        if st.button("Deep Dive Mode: create article outline", key="generate_deep_dive_outline"):
            outline_path = generate_deep_dive_outline(selected_topic_slug, selected_angle)
            if outline_path:
                st.success(f"Đã tạo outline: {outline_path}")
            else:
                st.warning("Không tạo được outline cho topic/angle này.")
        if not history_df.empty:
            with st.expander("Content angle history", expanded=False):
                st.dataframe(
                    history_df[["created_at", "topic", "angle", "platform", "content_style", "post_id", "status"]].tail(50),
                    use_container_width=True,
                    hide_index=True,
                )

    if calendar.empty:
        st.info("Chưa có social calendar. Chạy `python main.py` để tạo seed.")
        return

    f1, f2 = st.columns(2)
    platform_options = ["All"] + sorted(calendar["platform"].astype(str).unique().tolist())
    status_options = ["All"] + SOCIAL_REVIEW_STATUSES
    platform_filter = f1.selectbox("Lọc platform", platform_options, key="manual_social_platform")
    status_filter = f2.selectbox("Lọc status", status_options, key="manual_social_status")

    filtered = calendar.copy()
    if platform_filter != "All":
        filtered = filtered[filtered["platform"].astype(str) == platform_filter]
    if status_filter != "All":
        filtered = filtered[filtered["status"].astype(str) == status_filter]

    st.markdown("### Bài chờ duyệt")
    table_columns = ["id", "platform", "topic", "angle", "content_style", "post_title", "target_url", "status", "scheduled_date", "scheduled_time"]
    table_columns = [column for column in table_columns if column in filtered.columns]
    st.dataframe(
        filtered[table_columns],
        use_container_width=True,
        hide_index=True,
    )
    ready = calendar[calendar["status"].astype(str) == "Ready to Post"]
    if not ready.empty:
        st.markdown("### Ready to Post")
        st.info("Các bài này đã tới lịch nhưng Facebook/LinkedIn/X không auto-post. Hãy copy thủ công rồi bấm Mark Posted.")
        st.dataframe(
            ready[["id", "platform", "post_title", "scheduled_date", "scheduled_time", "target_url"]],
            use_container_width=True,
            hide_index=True,
        )
    failed = calendar[calendar["status"].astype(str) == "Failed"]
    if not failed.empty:
        st.markdown("### Failed / Retry queue")
        st.warning("Telegram auto failures can be retried up to 3 times. Use Retry Now to set the item back to Approved immediately.")
        st.dataframe(
            failed[["id", "platform", "post_title", "retry_count", "next_retry_time", "notes"]],
            use_container_width=True,
            hide_index=True,
        )

    if filtered.empty:
        st.info("Không có bài phù hợp bộ lọc.")
        return

    option_rows = filtered.to_dict("records")
    option_map = {
        f"{row.get('platform', '')} | {row.get('post_title', '')} | {row.get('id', '')}": str(row.get("id", ""))
        for row in option_rows
    }
    selected_label = st.selectbox("Chọn bài để preview", list(option_map.keys()), key="manual_social_selected")
    selected_id = option_map[selected_label]
    row = calendar[calendar["id"].astype(str) == selected_id].iloc[0].to_dict()
    st.markdown(f"### Preview: {row.get('post_title', '')}")
    st.caption(f"Platform: {row.get('platform', '')} | Status: {row.get('status', '')} | Schedule: {row.get('scheduled_date', '')} {row.get('scheduled_time', '')}")
    if row.get("content_style"):
        st.caption(f"Content style: {row.get('content_style')}")
    if row.get("topic") or row.get("angle"):
        st.caption(f"Topic: {row.get('topic', '')} | Angle: {row.get('angle', '')}")
    image_path = social_asset_path(selected_id)
    render_image_workflow(selected_id, image_path, row)
    post_body_value = str(row.get("post_body", ""))
    platform_key = str(row.get("platform", "")).lower()
    char_count = len(post_body_value)
    if platform_key == "x/twitter":
        render_x_thread_preview(row, selected_id, image_path)
    else:
        render_social_preview_card(row, selected_id, image_path)
        st.text_area("Nội dung copy-ready", value=post_body_value, height=260, key=f"manual_social_body_{selected_id}")
        st.caption(f"Character count: {char_count}")
    if platform_key in {"facebook", "linkedin"} and char_count < 400:
        st.warning("Bài Facebook/LinkedIn đang dưới 400 ký tự, nên viết dài hơn trước khi đăng.")
    elif platform_key == "telegram" and char_count < 400:
        st.info("Telegram có thể ngắn hơn, nhưng mục tiêu hiện tại là khoảng 700-1000 ký tự nếu cần kéo traffic tốt hơn.")
    same_article = calendar[
        calendar["target_url"].astype(str).map(base_social_url) == base_social_url(str(row.get("target_url", "")))
    ].copy()
    if len(same_article) > 1:
        st.markdown("#### Platform psychology versions")
        version_tabs = st.tabs(["Twitter version", "LinkedIn version", "Telegram version", "Facebook version"])
        platform_lookup = {
            "Twitter version": "X/Twitter",
            "LinkedIn version": "LinkedIn",
            "Telegram version": "Telegram",
            "Facebook version": "Facebook",
        }
        for tab, label in zip(version_tabs, platform_lookup):
            with tab:
                platform_name = platform_lookup[label]
                match = same_article[same_article["platform"].astype(str) == platform_name]
                if match.empty:
                    st.caption("Chưa có version cho platform này.")
                else:
                    item = match.iloc[0].to_dict()
                    body = str(item.get("post_body", ""))
                    st.caption(f"{platform_name} | {len(body)} ký tự | style: {item.get('content_style', '')}")
                    st.text_area(
                        f"{platform_name} copy",
                        value=body,
                        height=180,
                        disabled=True,
                        key=f"platform_version_{selected_id}_{platform_name}",
                    )
    st.caption("Link đã nằm trực tiếp trong nội dung bài. Không cần copy link riêng.")
    target_url = effective_social_url(row)
    action_columns = st.columns(5)
    with action_columns[0]:
        clipboard_button("Copy Content", post_body_value, f"copy_content_{selected_id}")
    with action_columns[1]:
        clipboard_button("Copy Link", target_url, f"copy_link_{selected_id}", toast_text="Copied link")
    with action_columns[2]:
        st.download_button(
            "Download .md",
            data=build_social_markdown(row, selected_id, image_path).encode("utf-8"),
            file_name=f"{selected_id}.md",
            mime="text/markdown",
            key=f"download_social_md_{selected_id}",
            use_container_width=True,
        )
    if image_path.exists():
        with action_columns[3]:
            open_image_button(image_path, f"open_image_{selected_id}")
        with action_columns[4]:
            st.download_button(
                "Download Image",
                data=image_path.read_bytes(),
                file_name=image_path.name,
                mime="image/png",
                key=f"download_image_{selected_id}",
                use_container_width=True,
            )
    elif str(row.get("platform", "")).lower() == "telegram":
        with action_columns[2]:
            channel_url = telegram_channel_link()
            if channel_url:
                st.link_button("Open Telegram Channel", channel_url, use_container_width=True)
            else:
                st.caption("Telegram channel link chưa cấu hình.")
    if image_path.exists() and str(row.get("platform", "")).lower() == "telegram":
        channel_url = telegram_channel_link()
        if channel_url:
            st.link_button("Open Telegram Channel", channel_url)
    post_pack = (
        f"Platform: {row.get('platform', '')}\n"
        f"Title: {row.get('post_title', '')}\n"
        f"ID: {selected_id}\n"
        f"Style: {row.get('content_style', '')}\n"
        f"Target URL: {target_url}\n"
        f"Image: {image_path if image_path.exists() else ''}\n\n"
        f"{post_body_value}"
    )
    clipboard_button("Copy Post Pack", post_pack, f"copy_pack_{selected_id}", toast_text="Copied post pack")
    render_link_health(target_url)
    note = st.text_input("Ghi chú khi cập nhật trạng thái", value=str(row.get("notes", "")), key=f"manual_social_note_{selected_id}")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Approved", key=f"manual_social_approve_{selected_id}"):
        update_calendar_status(selected_id, "Approved", note)
        st.success("Đã duyệt và lưu vào data/social_calendar.csv")
        st.rerun()
    if b2.button("Rejected", key=f"manual_social_reject_{selected_id}"):
        update_calendar_status(selected_id, "Rejected", note)
        st.success("Đã từ chối và lưu vào data/social_calendar.csv")
        st.rerun()
    if b3.button("Needs edit", key=f"manual_social_edit_{selected_id}"):
        update_calendar_status(selected_id, "Needs Edit", note)
        st.success("Đã đánh dấu cần chỉnh sửa.")
        st.rerun()
    if b4.button("Mark Posted", key=f"manual_social_posted_{selected_id}"):
        update_calendar_status(selected_id, "Posted", note)
        st.success("Đã đánh dấu đã đăng thủ công.")
        st.rerun()
    if row.get("status", "") == "Failed" and st.button("Retry Now", key=f"manual_social_retry_{selected_id}"):
        calendar_retry = load_social_calendar()
        mask = calendar_retry["id"].astype(str) == selected_id
        calendar_retry.loc[mask, "status"] = "Approved"
        calendar_retry.loc[mask, "next_retry_time"] = ""
        calendar_retry.loc[mask, "notes"] = "Retry requested from dashboard."
        save_social_calendar(calendar_retry)
        st.success("Đã đưa bài Failed về Approved để scheduler retry ngay.")
        st.rerun()

    st.markdown("### Export")
    st.download_button(
        "Download social_calendar.csv",
        data=load_social_calendar().to_csv(index=False).encode("utf-8-sig"),
        file_name="social_calendar.csv",
        mime="text/csv",
    )
    st.caption("Markdown copy files are saved in `draft_output/social_queue/`.")


def clipboard_button(label: str, value: str, key: str, toast_text: str = "Copied social content") -> None:
    safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(key))
    payload = json.dumps(str(value or ""))
    safe_toast = json.dumps(toast_text)
    components.html(
        f"""
        <div>
          <button id="copy-{safe_key}" style="
            border:1px solid #3b82f6;border-radius:8px;background:#1f2937;color:#f8fafc;
            padding:0.45rem 0.75rem;font-weight:600;cursor:pointer;width:100%;">
            {label}
          </button>
          <div id="toast-{safe_key}" style="
            visibility:hidden;margin-top:8px;background:#0f172a;color:#d1fae5;border:1px solid #10b981;
            border-radius:8px;padding:6px 10px;font-size:13px;">{toast_text}</div>
          <script>
            const btn_{safe_key} = document.getElementById('copy-{safe_key}');
            const toast_{safe_key} = document.getElementById('toast-{safe_key}');
            btn_{safe_key}.addEventListener('click', async () => {{
              const text = {payload};
              try {{
                await navigator.clipboard.writeText(text);
                toast_{safe_key}.textContent = {safe_toast};
              }} catch (e) {{
                const area = document.createElement('textarea');
                area.value = text;
                document.body.appendChild(area);
                area.select();
                document.execCommand('copy');
                area.remove();
                toast_{safe_key}.textContent = {safe_toast};
              }}
              toast_{safe_key}.style.visibility = 'visible';
              setTimeout(() => {{ toast_{safe_key}.style.visibility = 'hidden'; }}, 1800);
            }});
          </script>
        </div>
        """,
        height=74,
    )


def render_x_thread_preview(row: dict[str, object], selected_id: str, image_path: Path) -> None:
    st.markdown("#### X/Twitter thread composer")
    mode = st.selectbox(
        "Thread mode",
        X_THREAD_MODES,
        index=1 if "Viral thread" in X_THREAD_MODES else 0,
        key=f"x_thread_mode_{selected_id}",
    )
    original_body = str(row.get("post_body", ""))
    target_url = effective_social_url(row)
    title = str(row.get("post_title", "")).strip()
    style = str(row.get("content_style", "practical_review"))
    thread_posts = build_x_thread_preview(original_body, target_url, title, style, mode)
    thread_text = "\n\n".join(thread_posts)
    inject_x_preview_css()

    top_cols = st.columns([1, 1, 1, 1])
    with top_cols[0]:
        clipboard_button("Copy full thread", thread_text, f"copy_entire_thread_{selected_id}", toast_text="Copied thread")
    with top_cols[1]:
        st.download_button(
            "Download .txt",
            data=thread_text.encode("utf-8"),
            file_name=f"{selected_id}-x-thread.txt",
            mime="text/plain",
            key=f"download_x_thread_{selected_id}",
            use_container_width=True,
        )
    st.download_button(
        "Download markdown",
        data=build_thread_markdown(row, selected_id, image_path, thread_posts).encode("utf-8"),
        file_name=f"{selected_id}-x-thread.md",
        mime="text/markdown",
        key=f"download_x_thread_md_{selected_id}",
        use_container_width=True,
    )
    clipboard_button(
        "Copy CTA + Link + Hashtag",
        extract_cta_link_hashtag(thread_posts, target_url),
        f"copy_x_cta_link_hashtag_{selected_id}",
        toast_text="Copied CTA + link + hashtag",
    )
    with top_cols[2]:
        st.link_button("Open X Compose", "https://x.com/compose/post", use_container_width=True)
    with top_cols[3]:
        if image_path.exists():
            st.download_button(
                "Download image",
                data=image_path.read_bytes(),
                file_name=image_path.name,
                mime="image/png",
                key=f"download_x_image_{selected_id}",
                use_container_width=True,
            )
        else:
            st.caption("No image yet")

    st.markdown('<div class="x-thread-shell">', unsafe_allow_html=True)
    for index, post in enumerate(thread_posts, start=1):
        count = len(post)
        status = "OK" if count <= 280 else "Too long"
        status_class = "ok" if count <= 280 else "warn"
        st.markdown(
            f"""
            <div class="x-post-card">
              <div class="x-avatar">MS</div>
              <div class="x-post-body">
                <div class="x-post-meta">MS Smile AI Review Hub <span>@mssmileai</span> · Post {index}/{len(thread_posts)}</div>
                <div class="x-post-text">{html_escape(post).replace(chr(10), '<br>')}</div>
                <div class="x-post-footer"><span class="{status_class}">{status}</span> · {count}/280 chars</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        button_cols = st.columns([1, 4])
        with button_cols[0]:
            clipboard_button(f"Copy Post {index}", post, f"copy_x_post_{selected_id}_{index}", toast_text=f"Copied post {index}")
    st.markdown("</div>", unsafe_allow_html=True)

    if image_path.exists():
        st.image(str(image_path), caption=f"Selected social image: {image_path.name}", use_container_width=True)
    if any(len(post) > 280 for post in thread_posts):
        st.warning("Có post vượt 280 ký tự. Hãy đổi mode hoặc rút gọn hook.")
    render_link_health(target_url)
    st.caption("Open X Compose chỉ mở trang soạn bài. Hãy paste thủ công từng post/thread. Dashboard không gọi API X và không tự đăng.")
    st.caption("Link/CTA/hashtag được đưa vào post cuối. X/Facebook/LinkedIn vẫn manual-only, không auto-post.")


def render_image_workflow(selected_id: str, image_path: Path, row: dict[str, object]) -> None:
    st.markdown("#### Image workflow")
    cols = st.columns([1.2, 1, 1])
    with cols[0]:
        uploaded = st.file_uploader(
            "Upload thumbnail/social image",
            type=["png", "jpg", "jpeg"],
            key=f"social_image_upload_{selected_id}",
        )
        if uploaded is not None:
            save_uploaded_social_image(uploaded, image_path)
            st.success(f"Saved image: {image_path.name}")
            st.rerun()
    with cols[1]:
        if image_path.exists():
            open_image_button(image_path, f"open_social_image_{selected_id}")
        else:
            st.caption("No image selected")
    with cols[2]:
        if image_path.exists():
            st.download_button(
                "Download image",
                data=image_path.read_bytes(),
                file_name=image_path.name,
                mime="image/png",
                key=f"download_social_image_top_{selected_id}",
                use_container_width=True,
            )
    if image_path.exists():
        try:
            with Image.open(image_path) as image:
                width, height = image.size
            shape = "square" if abs(width - height) < 8 else "landscape" if width > height else "portrait"
            size_kb = image_path.stat().st_size / 1024
            st.caption(f"Selected image: {image_path.name} | {size_kb:.1f} KB | {width}x{height} | {shape} preview")
        except Exception:
            st.caption(f"Selected image: {image_path.name}")
        st.image(str(image_path), caption=f"{row.get('platform', '')} social preview image", use_container_width=True)
    else:
        st.info("No image attached yet. Upload a square or landscape image for X/LinkedIn/Facebook preview.")


def render_social_preview_card(row: dict[str, object], selected_id: str, image_path: Path) -> None:
    platform = str(row.get("platform", "Social"))
    body = str(row.get("post_body", ""))
    title = str(row.get("post_title", ""))
    target_url = effective_social_url(row)
    inject_social_preview_css()
    platform_class = platform.lower().replace("/", "-").replace(" ", "-")
    preview_text = html_escape(body).replace(chr(10), "<br>")
    image_html = ""
    if image_path.exists():
        image_src = image_path.as_posix()
        image_html = f'<img class="social-preview-img" src="{image_src}" alt="{html_escape(title)} preview image">'
    st.markdown(
        f"""
        <div class="social-preview-card {platform_class}">
          <div class="social-preview-top">
            <div class="social-preview-avatar">MS</div>
            <div>
              <div class="social-preview-name">MS Smile AI Review Hub</div>
              <div class="social-preview-meta">{html_escape(platform)} preview · copy-ready</div>
            </div>
          </div>
          {image_html}
          <div class="social-preview-title">{html_escape(title)}</div>
          <div class="social-preview-text">{preview_text}</div>
          <div class="social-preview-link">{html_escape(target_url)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_social_preview_css() -> None:
    st.markdown(
        """
        <style>
        .social-preview-card {
            background:#101827;border:1px solid #26364d;border-radius:18px;padding:18px;margin:12px 0 18px 0;
            color:#e5edf8;box-shadow:0 10px 26px rgba(0,0,0,.2);
        }
        .social-preview-top {display:flex;align-items:center;gap:12px;margin-bottom:14px;}
        .social-preview-avatar {
            width:42px;height:42px;border-radius:50%;background:#2563eb;color:white;font-weight:800;
            display:flex;align-items:center;justify-content:center;flex:0 0 42px;
        }
        .social-preview-name {font-weight:800;}
        .social-preview-meta {font-size:13px;color:#93a4bc;}
        .social-preview-img {width:100%;border-radius:14px;border:1px solid #2b3a52;margin:8px 0 14px 0;}
        .social-preview-title {font-weight:800;font-size:18px;margin-bottom:8px;}
        .social-preview-text {font-size:15.5px;line-height:1.55;}
        .social-preview-link {margin-top:14px;color:#93c5fd;font-size:13px;word-break:break-all;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_social_markdown(row: dict[str, object], selected_id: str, image_path: Path) -> str:
    return (
        f"# {row.get('post_title', '')}\n\n"
        f"- ID: {selected_id}\n"
        f"- Platform: {row.get('platform', '')}\n"
        f"- Status: {row.get('status', '')}\n"
        f"- Style: {row.get('content_style', '')}\n"
        f"- Target URL: {effective_social_url(row)}\n"
        f"- Image: {image_path if image_path.exists() else ''}\n\n"
        "## Copy\n\n"
        f"{row.get('post_body', '')}\n"
    )


def build_thread_markdown(row: dict[str, object], selected_id: str, image_path: Path, posts: list[str]) -> str:
    parts = [
        f"# {row.get('post_title', '')}",
        "",
        f"- ID: {selected_id}",
        f"- Platform: {row.get('platform', '')}",
        f"- Style: {row.get('content_style', '')}",
        f"- Target URL: {effective_social_url(row)}",
        f"- Image: {image_path if image_path.exists() else ''}",
        "",
    ]
    for index, post in enumerate(posts, start=1):
        parts.extend([f"## Post {index}", "", post, ""])
    return "\n".join(parts)


def effective_social_url(row: dict[str, object]) -> str:
    return str(row.get("short_url", "") or row.get("target_url", "")).strip()


def extract_cta_link_hashtag(posts: list[str], target_url: str) -> str:
    if posts:
        final = posts[-1]
        if target_url and target_url not in final:
            return f"{final}\n{target_url}"
        return final
    return target_url


def render_link_health(target_url: str) -> None:
    st.caption(f"Link đang dùng: {target_url or '(empty)'}")
    allowed_domains = (
        "https://review.mssmileenglish.com",
        "https://tuanpk1977.github.io/affiliate-bot",
    )
    if not target_url:
        st.error("Target URL đang trống.")
    elif not target_url.startswith(("http://", "https://")):
        st.warning("Target URL thiếu http/https.")
    elif target_url.startswith(allowed_domains):
        st.success("Target URL OK: dùng domain được phép.")
    else:
        st.warning("Cảnh báo: link không thuộc review.mssmileenglish.com hoặc tuanpk1977.github.io/affiliate-bot.")


def save_uploaded_social_image(uploaded_file: object, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(uploaded_file) as image:
        image.convert("RGB").save(output_path, format="PNG")


def html_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def inject_x_preview_css() -> None:
    st.markdown(
        """
        <style>
        .x-thread-shell {display:flex;flex-direction:column;gap:14px;margin:12px 0 18px 0;}
        .x-post-card {
            display:flex;gap:12px;background:#0f172a;border:1px solid #263244;border-radius:18px;
            padding:16px 18px;margin:10px 0;color:#e5edf8;box-shadow:0 10px 26px rgba(0,0,0,.22);
        }
        .x-avatar {
            width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;
            background:#2563eb;color:#fff;font-weight:800;flex:0 0 42px;
        }
        .x-post-body {flex:1;min-width:0;}
        .x-post-meta {font-weight:700;color:#f8fafc;margin-bottom:8px;}
        .x-post-meta span {font-weight:500;color:#93a4bc;}
        .x-post-text {font-size:16px;line-height:1.48;white-space:normal;}
        .x-post-footer {margin-top:10px;color:#93a4bc;font-size:13px;}
        .x-post-footer .ok {color:#86efac;font-weight:700;}
        .x-post-footer .warn {color:#fca5a5;font-weight:700;}
        @media (max-width: 640px) {
            .x-post-card {padding:14px 12px;border-radius:14px;}
            .x-avatar {width:34px;height:34px;flex-basis:34px;font-size:12px;}
            .x-post-text {font-size:15px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def image_data_uri(path: Path) -> str:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{encoded}"


def open_image_button(path: Path, key: str) -> None:
    uri = image_data_uri(path)
    if not uri:
        return
    components.html(
        f"""
        <a href="{uri}" target="_blank" download="{path.name}" style="
          display:block;text-align:center;border:1px solid #64748b;border-radius:8px;
          background:#111827;color:#f8fafc;padding:0.48rem 0.75rem;
          font-weight:600;text-decoration:none;">Open Image</a>
        """,
        height=42,
    )


def telegram_channel_link() -> str:
    env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    config_chat = ""
    config_path = settings.base_dir / "config" / "social_accounts.json"
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            telegram = payload.get("telegram", {}) if isinstance(payload, dict) else {}
            if isinstance(telegram, dict):
                config_chat = str(telegram.get("telegram_chat_id") or telegram.get("chat_id") or "").strip()
        except Exception:
            config_chat = ""
    chat = env_chat or config_chat
    if chat.startswith("@"):
        return f"https://t.me/{chat.lstrip('@')}"
    if chat.startswith("https://t.me/"):
        return chat
    return ""


def split_x_thread(content: str) -> list[str]:
    posts: list[str] = []
    current: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line[:2] in {"1/", "2/", "3/", "4/", "5/", "6/", "7/", "8/", "9/"} and current:
            posts.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        posts.append("\n".join(current).strip())
    return posts


def base_social_url(value: str) -> str:
    return str(value or "").split("?", 1)[0].rstrip("/")


def render_post_deploy_page() -> None:
    st.header("Post Deploy Kit")
    st.warning("Local-only helper. No Google API, no social API, no auto-posting, no deploy.")

    if st.button("Regenerate post-deploy kit", key="regenerate_post_deploy_kit"):
        result = run_post_deploy_kit()
        st.success(f"Generated local kit: {result}")

    indexing = read_csv(settings.data_dir / "indexing_priority.csv")
    social_ready = read_csv(settings.data_dir / "social_posting_queue.csv")
    click_report = load_click_tracking_report()
    go_count = go_page_count()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Priority URLs", len(indexing))
    c2.metric("Social copy-ready", len(social_ready))
    c3.metric("/go/ tracking pages", go_count)
    total_clicks = int(pd.to_numeric(click_report.get("clicks", pd.Series(dtype=str)), errors="coerce").fillna(0).sum()) if not click_report.empty else 0
    c4.metric("Tracked clicks", total_clicks)

    st.markdown("### Google Indexing Kit")
    if indexing.empty:
        st.info("No indexing priority data yet. Click regenerate or run python main.py.")
    else:
        st.dataframe(indexing, use_container_width=True, hide_index=True)
        st.download_button("Download indexing_priority.csv", indexing.to_csv(index=False).encode("utf-8-sig"), "indexing_priority.csv", "text/csv")
    checklist_path = settings.data_dir / "google_indexing_checklist.md"
    if checklist_path.exists():
        st.caption(f"Checklist file: {checklist_path}")
        st.text_area("Google indexing checklist", checklist_path.read_text(encoding="utf-8"), height=220, disabled=True)

    st.markdown("### Social Posting Kit")
    if social_ready.empty:
        st.info("No copy-ready social posts yet. Generate social variations first.")
    else:
        st.dataframe(social_ready, use_container_width=True, hide_index=True)
        st.download_button("Download social_posting_queue.csv", social_ready.to_csv(index=False).encode("utf-8-sig"), "social_posting_queue.csv", "text/csv")
        image_candidates = [str(path) for path in social_ready.get("image_path", pd.Series(dtype=str)).astype(str).tolist() if path and Path(path).exists()]
        if image_candidates:
            st.image(image_candidates[0], caption="Thumbnail preview", use_container_width=True)
        st.caption("Copy-ready files are saved in draft_output/social_ready/.")

    st.markdown("### Traffic & Click Tracking")
    if click_report.empty:
        st.warning("Chưa có click data thật. Hãy đăng social và cập nhật impressions/clicks thủ công.")
    else:
        st.dataframe(click_report, use_container_width=True, hide_index=True)
        clicks_numeric = pd.to_numeric(click_report["clicks"], errors="coerce").fillna(0)
        if clicks_numeric.sum() <= 0:
            st.warning("Chưa có click data thật. Hãy đăng social và cập nhật impressions/clicks thủ công.")
        else:
            top_article = click_report.assign(_clicks=clicks_numeric).sort_values("_clicks", ascending=False).head(10)
            st.markdown("#### Top article by clicks")
            st.dataframe(top_article[["article_url", "platform", "clicks", "impressions", "ctr"]], use_container_width=True, hide_index=True)
            st.markdown("#### Top platform by clicks")
            st.dataframe(click_report.assign(_clicks=clicks_numeric).groupby("platform")["_clicks"].sum().reset_index(name="clicks").sort_values("clicks", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Post Deploy Checklist")
    current = load_post_deploy_checklist()
    updated = {}
    cols = st.columns(2)
    for idx, item in enumerate(CHECKLIST_ITEMS):
        with cols[idx % 2]:
            updated[item] = st.checkbox(item, value=bool(current.get(item, False)), key=f"post_deploy_{idx}")
    if st.button("Save post deploy checklist", key="save_post_deploy_checklist"):
        save_post_deploy_checklist(updated)
        st.success("Saved config/post_deploy_checklist.json")


def render_seo_system_page() -> None:
    st.header("SEO System")
    st.warning("Local-only SEO/tracking reports. Không gọi Google API, không deploy, không auto-post.")
    seo_audit = read_csv(settings.data_dir / "seo_audit_report.csv")
    topical_map = read_csv(settings.data_dir / "topical_map.csv")
    tracking_map = read_csv(settings.data_dir / "link_tracking_map.csv")
    quality = read_csv(settings.data_dir / "content_quality_report.csv")
    affiliate_tracking = read_csv(settings.data_dir / "affiliate_tracking_report.csv")
    redirect_map = read_csv(settings.data_dir / "redirect_map.csv")
    keyword_report = read_csv(settings.data_dir / "keyword_intelligence_report.csv")
    action_priority = read_csv(settings.data_dir / "action_priority_report.csv")
    page_tracking = read_csv(settings.data_dir / "seo_tracking_page_report.csv")
    social_assets = read_csv(settings.data_dir / "seo_social_assets_report.csv")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SEO audit pages", len(seo_audit))
    c2.metric("Topical map rows", len(topical_map))
    c3.metric("Tracked social links", len(tracking_map))
    warning_count = int((quality.get("recommendation", pd.Series(dtype=str)).astype(str) != "ok").sum()) if not quality.empty else 0
    c4.metric("Quality warnings", warning_count)

    st.markdown("### SEO audit summary")
    if seo_audit.empty:
        st.info("Chưa có seo_audit_report.csv. Hãy chạy python main.py.")
    else:
        warn_rows = seo_audit[seo_audit["warnings"].astype(str).str.len() > 0] if "warnings" in seo_audit.columns else pd.DataFrame()
        st.caption(f"Rows with warnings: {len(warn_rows)}")
        st.dataframe(warn_rows.head(50) if not warn_rows.empty else seo_audit.head(50), use_container_width=True, hide_index=True)
        st.download_button("Download seo_audit_report.csv", seo_audit.to_csv(index=False).encode("utf-8-sig"), "seo_audit_report.csv", "text/csv")

    st.markdown("### Page SEO + Tracking report")
    if page_tracking.empty:
        st.info("No seo_tracking_page_report.csv yet. Run python main.py.")
    else:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Main pages", len(page_tracking))
        s2.metric("Pages with CTA", int((page_tracking.get("cta_links_count", pd.Series(dtype=int)).astype(int) > 0).sum()))
        s3.metric("Hreflang OK", int((page_tracking.get("hreflang_status", pd.Series(dtype=str)).astype(str) == "ok").sum()))
        s4.metric("In sitemap", int((page_tracking.get("sitemap_included", pd.Series(dtype=str)).astype(str) == "yes").sum()))
        st.dataframe(page_tracking.head(80), use_container_width=True, hide_index=True)
        st.download_button("Download seo_tracking_page_report.csv", page_tracking.to_csv(index=False).encode("utf-8-sig"), "seo_tracking_page_report.csv", "text/csv")

    st.markdown("### Topical map summary")
    if topical_map.empty:
        st.info("Chưa có topical_map.csv.")
    else:
        if "topic_group" in topical_map.columns:
            st.dataframe(topical_map.groupby("topic_group").size().reset_index(name="pages"), use_container_width=True, hide_index=True)
        st.download_button("Download topical_map.csv", topical_map.to_csv(index=False).encode("utf-8-sig"), "topical_map.csv", "text/csv")

    st.markdown("### Tracking map summary")
    if tracking_map.empty:
        st.info("Chưa có link_tracking_map.csv.")
    else:
        if "platform" in tracking_map.columns:
            st.dataframe(tracking_map.groupby("platform").size().reset_index(name="links"), use_container_width=True, hide_index=True)
        missing_utm = tracking_map[tracking_map.get("has_utm", pd.Series(dtype=str)).astype(str) != "true"] if "has_utm" in tracking_map.columns else pd.DataFrame()
        if not missing_utm.empty:
            st.warning(f"Có {len(missing_utm)} social links chưa đủ UTM.")
            st.dataframe(missing_utm.head(30), use_container_width=True, hide_index=True)
        st.download_button("Download link_tracking_map.csv", tracking_map.to_csv(index=False).encode("utf-8-sig"), "link_tracking_map.csv", "text/csv")

    st.markdown("### Content quality warnings")
    if quality.empty:
        st.info("Chưa có content_quality_report.csv.")
    else:
        warnings = quality[quality["recommendation"].astype(str) != "ok"] if "recommendation" in quality.columns else quality
        st.dataframe(warnings.head(80), use_container_width=True, hide_index=True)
        st.download_button("Download content_quality_report.csv", quality.to_csv(index=False).encode("utf-8-sig"), "content_quality_report.csv", "text/csv")

    st.markdown("### SEO Social Assets")
    if social_assets.empty:
        st.info("No seo_social_assets_report.csv yet. Run python main.py.")
    else:
        st.dataframe(social_assets.groupby(["language", "platform"]).size().reset_index(name="drafts"), use_container_width=True, hide_index=True)
        st.download_button("Download seo_social_assets_report.csv", social_assets.to_csv(index=False).encode("utf-8-sig"), "seo_social_assets_report.csv", "text/csv")

    st.divider()
    st.markdown("## Affiliate Tracking")
    t1, t2, t3 = st.columns(3)
    t1.metric("Tracking links", len(affiliate_tracking))
    t2.metric("Redirect pages", len(redirect_map))
    rec_count = affiliate_tracking["recommendation"].nunique() if not affiliate_tracking.empty and "recommendation" in affiliate_tracking.columns else 0
    t3.metric("Recommendation types", rec_count)
    if affiliate_tracking.empty:
        st.info("Chưa có affiliate_tracking_report.csv. Hãy chạy python main.py.")
    else:
        if "source" in affiliate_tracking.columns:
            st.caption("Link count by source/platform")
            st.dataframe(affiliate_tracking.groupby(["source", "platform"]).size().reset_index(name="links"), use_container_width=True, hide_index=True)
        if "recommendation" in affiliate_tracking.columns:
            st.caption("Recommendation queue")
            st.dataframe(
                affiliate_tracking[["tracking_id", "source", "platform", "page_slug", "tool_name", "status", "recommendation"]].head(80),
                use_container_width=True,
                hide_index=True,
            )
        cta1, cta2 = st.columns(2)
        cta1.download_button(
            "Download affiliate_tracking_report.csv",
            affiliate_tracking.to_csv(index=False).encode("utf-8-sig"),
            "affiliate_tracking_report.csv",
            "text/csv",
        )
        cta2.download_button(
            "Download redirect_map.csv",
            redirect_map.to_csv(index=False).encode("utf-8-sig"),
            "redirect_map.csv",
            "text/csv",
        )

    st.divider()
    st.markdown("## Keyword Intelligence")
    k1, k2, k3 = st.columns(3)
    k1.metric("Keywords", len(keyword_report))
    high_priority = int((keyword_report.get("priority_score", pd.Series(dtype=float)).astype(float) >= 70).sum()) if not keyword_report.empty and "priority_score" in keyword_report.columns else 0
    k2.metric("High priority", high_priority)
    gap_count = keyword_report["content_gap"].nunique() if not keyword_report.empty and "content_gap" in keyword_report.columns else 0
    k3.metric("Gap types", gap_count)
    if keyword_report.empty:
        st.info("Chưa có keyword_intelligence_report.csv. Hãy chạy python main.py.")
    else:
        filter_cols = st.columns(2)
        intents = ["All"] + sorted(keyword_report["intent"].dropna().astype(str).unique().tolist()) if "intent" in keyword_report.columns else ["All"]
        clusters = ["All"] + sorted(keyword_report["topic_cluster"].dropna().astype(str).unique().tolist()) if "topic_cluster" in keyword_report.columns else ["All"]
        intent_filter = filter_cols[0].selectbox("Intent", intents, key="seo_system_keyword_intent")
        cluster_filter = filter_cols[1].selectbox("Topic cluster", clusters, key="seo_system_keyword_cluster")
        filtered_keywords = keyword_report.copy()
        if intent_filter != "All" and "intent" in filtered_keywords.columns:
            filtered_keywords = filtered_keywords[filtered_keywords["intent"].astype(str) == intent_filter]
        if cluster_filter != "All" and "topic_cluster" in filtered_keywords.columns:
            filtered_keywords = filtered_keywords[filtered_keywords["topic_cluster"].astype(str) == cluster_filter]
        st.caption("Top 20 keyword priority")
        st.dataframe(filtered_keywords.head(20), use_container_width=True, hide_index=True)
        if "content_gap" in keyword_report.columns:
            st.caption("Content gap summary")
            st.dataframe(keyword_report.groupby("content_gap").size().reset_index(name="keywords"), use_container_width=True, hide_index=True)
        st.download_button(
            "Download keyword_intelligence_report.csv",
            keyword_report.to_csv(index=False).encode("utf-8-sig"),
            "keyword_intelligence_report.csv",
            "text/csv",
        )

    st.divider()
    st.markdown("## Next Best Actions / Hành động ưu tiên tiếp theo")
    if action_priority.empty:
        st.info("Chưa có action_priority_report.csv. Hãy chạy python main.py.")
    else:
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Total action items", len(action_priority))
        high_items = int(action_priority["expected_impact"].astype(str).str.lower().eq("high").sum()) if "expected_impact" in action_priority.columns else 0
        a2.metric("High priority items", high_items)
        improve_items = int(action_priority["action_type"].astype(str).eq("improve_existing_article").sum()) if "action_type" in action_priority.columns else 0
        a3.metric("Articles to improve", improve_items)
        new_items = int(action_priority["action_type"].astype(str).eq("write_new_article").sum()) if "action_type" in action_priority.columns else 0
        a4.metric("New articles", new_items)
        social_items = int(action_priority["action_type"].astype(str).eq("push_social").sum()) if "action_type" in action_priority.columns else 0
        a5.metric("Social pushes", social_items)
        cta_items = int(action_priority["action_type"].astype(str).eq("improve_cta").sum()) if "action_type" in action_priority.columns else 0
        a6.metric("CTA issues", cta_items)

        filters = st.columns(2)
        action_types = ["All"] + sorted(action_priority["action_type"].dropna().astype(str).unique().tolist()) if "action_type" in action_priority.columns else ["All"]
        topics = ["All"] + sorted(action_priority["topic"].dropna().astype(str).unique().tolist()) if "topic" in action_priority.columns else ["All"]
        action_filter = filters[0].selectbox("Action type", action_types, key="seo_system_action_type")
        topic_filter = filters[1].selectbox("Topic", topics, key="seo_system_action_topic")
        filtered_actions = action_priority.copy()
        if action_filter != "All" and "action_type" in filtered_actions.columns:
            filtered_actions = filtered_actions[filtered_actions["action_type"].astype(str) == action_filter]
        if topic_filter != "All" and "topic" in filtered_actions.columns:
            filtered_actions = filtered_actions[filtered_actions["topic"].astype(str) == topic_filter]
        st.caption("Top 20 việc nên làm tiếp")
        st.dataframe(filtered_actions.head(20), use_container_width=True, hide_index=True)
        if not filtered_actions.empty:
            st.markdown("### Execute selected action")
            options = []
            labels = {}
            for idx, row in filtered_actions.head(100).iterrows():
                label = f"#{row.get('priority_rank')} | {row.get('action_type')} | {row.get('keyword') or row.get('page_url')}"
                key = str(idx)
                options.append(key)
                labels[key] = label
            selected_key = st.selectbox(
                "Select action item",
                options,
                format_func=lambda value: labels.get(value, value),
                key="seo_system_selected_action",
            )
            selected_action = filtered_actions.loc[int(selected_key)].fillna("").to_dict()
            detail_cols = [
                "priority_rank",
                "action_type",
                "topic",
                "keyword",
                "page_url",
                "platform",
                "reason",
                "expected_impact",
                "difficulty",
                "next_action",
            ]
            st.dataframe(pd.DataFrame([{column: selected_action.get(column, "") for column in detail_cols}]), use_container_width=True, hide_index=True)
            b1, b2, b3, b4, b5 = st.columns(5)
            if b1.button("Generate Article Draft", key="generate_action_article_draft"):
                path = generate_action_article_draft(selected_action)
                st.success(f"Draft created: {path}")
            if b2.button("Generate Social Pack", key="generate_action_social_pack"):
                paths = generate_action_social_pack(selected_action)
                st.success("Social pack created: " + ", ".join(str(path) for path in paths.values()))
            if b3.button("Generate Internal Link Plan", key="generate_action_internal_link_plan"):
                path = generate_action_internal_link_plan(selected_action)
                st.success(f"Internal link plan updated: {path}")
            if b4.button("Mark As Done", key="mark_action_done"):
                path = mark_action_status(selected_action, "done", "Marked done from SEO System dashboard")
                st.success(f"Action status updated: {path}")
            b5.download_button(
                "Export Selected Action",
                pd.DataFrame([selected_action]).to_csv(index=False).encode("utf-8-sig"),
                file_name=f"action-{selected_action.get('priority_rank', 'selected')}.csv",
                mime="text/csv",
            )
        st.download_button(
            "Download action_priority_report.csv",
            action_priority.to_csv(index=False).encode("utf-8-sig"),
            "action_priority_report.csv",
            "text/csv",
        )


def render_performance_intelligence_page() -> None:
    st.header("Performance Intelligence")
    st.caption("Local-safe performance view. Import Google Search Console exports manually; no Google API is called.")

    traffic = read_csv(settings.data_dir / "traffic_performance_report.csv")
    gsc_pages = read_csv(settings.data_dir / "gsc_page_performance_report.csv")
    gsc_queries = read_csv(settings.data_dir / "gsc_query_performance_report.csv")
    go_clicks = read_csv(settings.data_dir / "go_click_performance_report.csv")
    actions = read_csv(settings.data_dir / "action_priority_report.csv")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked pages", len(traffic))
    total_clicks = int(pd.to_numeric(traffic.get("clicks", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not traffic.empty else 0
    total_impressions = int(pd.to_numeric(traffic.get("impressions", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not traffic.empty else 0
    c2.metric("GSC clicks", total_clicks)
    c3.metric("GSC impressions", total_impressions)
    go_total = int(pd.to_numeric(go_clicks.get("clicks", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not go_clicks.empty else 0
    c4.metric("/go clicks", go_total)

    if traffic.empty:
        st.info("No traffic_performance_report.csv yet. Run python main.py or python scripts/import_gsc_export.py.")
    else:
        st.markdown("### Top Pages")
        sort_cols = [col for col in ["priority_score", "clicks", "impressions"] if col in traffic.columns]
        top_pages = traffic.sort_values(sort_cols, ascending=False) if sort_cols else traffic
        display_cols = [col for col in ["page", "title_or_slug", "impressions", "clicks", "ctr", "avg_position", "cta_clicks", "internal_links_count", "priority_score", "recommended_action"] if col in top_pages.columns]
        st.dataframe(top_pages[display_cols].head(50), use_container_width=True, hide_index=True)
        st.download_button("Download traffic_performance_report.csv", traffic.to_csv(index=False).encode("utf-8-sig"), "traffic_performance_report.csv", "text/csv")

    st.markdown("### Top Queries")
    if gsc_queries.empty:
        st.info("No GSC query data yet. Export queries from Google Search Console and save them as data/gsc_performance_import.csv.")
    else:
        sort_cols = [col for col in ["clicks", "impressions"] if col in gsc_queries.columns]
        top_queries = gsc_queries.sort_values(sort_cols, ascending=False) if sort_cols else gsc_queries
        st.dataframe(top_queries.head(50), use_container_width=True, hide_index=True)
        st.download_button("Download gsc_query_performance_report.csv", gsc_queries.to_csv(index=False).encode("utf-8-sig"), "gsc_query_performance_report.csv", "text/csv")

    st.markdown("### CTA / Go Clicks")
    if go_clicks.empty:
        st.info("No go_click_performance_report.csv yet. The report is still safe when no click data exists.")
    else:
        st.dataframe(go_clicks.head(80), use_container_width=True, hide_index=True)
        st.download_button("Download go_click_performance_report.csv", go_clicks.to_csv(index=False).encode("utf-8-sig"), "go_click_performance_report.csv", "text/csv")

    st.markdown("### Next Best Actions")
    if traffic.empty and actions.empty:
        st.info("No action data yet. Run python main.py.")
    else:
        if not traffic.empty and "recommended_action" in traffic.columns:
            st.caption("Performance-based actions")
            action_view = traffic[traffic["recommended_action"].astype(str) != "monitor"] if "recommended_action" in traffic.columns else traffic
            st.dataframe(action_view.head(30), use_container_width=True, hide_index=True)
        if not actions.empty:
            st.caption("Existing action priority report")
            cols = [col for col in ["priority_rank", "action_type", "topic", "keyword", "page_url", "reason", "expected_impact", "next_action"] if col in actions.columns]
            st.dataframe(actions[cols].head(20), use_container_width=True, hide_index=True)

    st.markdown("### Manual GSC Import")
    st.write("1. Export page/query data from Google Search Console.")
    st.write("2. Save it as `data/gsc_performance_import.csv` with columns from `data/gsc_performance_import_template.csv`.")
    st.write("3. Run `python scripts/import_gsc_export.py` or `python main.py`.")


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "allowed"}


def extract_review_parts(content: str) -> dict[str, str]:
    text = str(content or "")

    def between(starts: list[str], ends: list[str]) -> str:
        lower = text.lower()
        start_pos = -1
        start_token = ""
        for token in starts:
            pos = lower.find(token.lower())
            if pos != -1 and (start_pos == -1 or pos < start_pos):
                start_pos = pos
                start_token = token
        if start_pos == -1:
            return ""
        start = start_pos + len(start_token)
        end_candidates = [lower.find(token.lower(), start) for token in ends if lower.find(token.lower(), start) != -1]
        end = min(end_candidates) if end_candidates else len(text)
        return text[start:end].strip()

    return {
        "seo_meta": between(["Meta title:", "Meta description:"], ["Intro:", "Sections:", "FAQ:"]),
        "faq": between(["FAQ:"], ["CTA:", "Internal links:", "Affiliate disclosure:"]),
        "cta": between(["CTA:"], ["Internal links:", "Affiliate disclosure:"]),
        "internal_links": between(["Internal links:"], ["Affiliate disclosure:", "Disclosure:"]),
        "affiliate_disclosure": between(["Affiliate disclosure:", "Disclosure:"], []),
    }


def count_site_pages(pattern: str) -> int:
    return len(list(settings.site_output_dir.glob(pattern))) if settings.site_output_dir.exists() else 0


def sitemap_url_count() -> int:
    sitemap = settings.site_output_dir / "sitemap.xml"
    if not sitemap.exists():
        return 0
    return sitemap.read_text(encoding="utf-8", errors="ignore").count("<loc>")


def recommended_to_test(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (pd.to_numeric(df["total_score"], errors="coerce") >= 80)
        & (df["risk_level"].isin(["Low", "Medium"]))
        & (pd.to_numeric(df["estimated_roi"], errors="coerce") > 0)
        & (df["compliance_status"] != "BLOCKED")
        & (df["competition"].isin(["Low", "Medium"]))
    ].sort_values(["total_score", "estimated_roi"], ascending=False).head(6)


def display_offer_table(df: pd.DataFrame) -> pd.DataFrame:
    table = rename_for_display(
        df,
        {
            "brand_name": "Tên thương hiệu",
            "niche": "Ngách",
            "total_score": "Điểm tổng",
            "grade": "Xếp hạng",
            "risk_level": "Mức rủi ro",
            "trend": "Xu hướng",
            "competition": "Mức cạnh tranh",
            "buyer_intent_label": "Buyer Intent",
            "estimated_roi": "ROI dự kiến",
            "data_confidence": "Độ tin cậy dữ liệu",
            "recommendation": "Khuyến nghị",
        },
    )
    if table.empty:
        return table
    table["Mức rủi ro"] = table["Mức rủi ro"].map(risk_label)
    table["Xu hướng"] = table["Xu hướng"].map(trend_label)
    table["Mức cạnh tranh"] = table["Mức cạnh tranh"].map(competition_label)
    return table


def build_positive_reasons(row: pd.Series) -> list[str]:
    items = []
    if to_bool(row.get("recurring")):
        items.append("Hoa hồng recurring tốt.")
    if str(row.get("buyer_intent_label", "")) == "High":
        items.append("Nhu cầu tìm kiếm có buyer intent cao.")
    if str(row.get("google_ads_policy", "")) != "BLOCKED" or str(row.get("bing_ads_policy", "")) != "BLOCKED":
        items.append("Có thể test Google/Bing Search với landing page review.")
    if float(row.get("estimated_roi") or 0) > 0:
        items.append("ROI dự kiến đang dương.")
    if str(row.get("data_confidence", "")) == "LOW":
        items.append("Chỉ nên xem là shortlist vì dữ liệu chưa xác minh.")
    return items or ["Cần thêm dữ liệu trước khi test."]


def build_risk_reasons(row: pd.Series) -> list[str]:
    notes = str(row.get("policy_notes", "")).split("|")
    items = [note.strip() for note in notes if note.strip()]
    if str(row.get("data_confidence", "")) == "LOW":
        items.append("Dữ liệu hiện tại là mẫu/rule-based, chưa xác minh nguồn thật.")
    if not items:
        items.append("Vẫn cần kiểm tra affiliate policy thật.")
    if "Không được bid từ khóa thương hiệu." not in items and not to_bool(row.get("brand_bidding_allowed")):
        items.append("Không được bid từ khóa thương hiệu.")
    return items


def build_strategy(row: pd.Series) -> list[str]:
    strategy = [
        "Chạy keyword so sánh và review trước.",
        "Test ngân sách nhỏ 10-20 USD/ngày.",
        "Dùng landing page review thay vì link trực tiếp.",
    ]
    if str(row.get("competition", "")) == "High":
        strategy.append("Tránh broad keyword vì mức cạnh tranh cao.")
    if str(row.get("data_confidence", "")) == "LOW":
        strategy.append("Xác minh affiliate terms và payout trước khi upload CSV.")
    return strategy


def translate_profit_result(result: dict) -> dict:
    return {
        "Ngân sách/ngày": result.get("daily_budget"),
        "CPC dự kiến": result.get("assumed_cpc"),
        "CTR dự kiến": result.get("assumed_ctr"),
        "Tỷ lệ chuyển đổi dự kiến": result.get("assumed_conversion_rate"),
        "Click dự kiến": result.get("expected_clicks"),
        "Chuyển đổi dự kiến": result.get("expected_conversions"),
        "Doanh thu dự kiến": result.get("expected_revenue"),
        "ROI dự kiến": result.get("expected_roi"),
        "Lợi nhuận dự kiến": result.get("expected_profit"),
        "CPA hòa vốn": result.get("break_even_cpa"),
    }


def display_data_sources(data_sources: pd.DataFrame) -> pd.DataFrame:
    df = data_sources.copy()
    if df.empty:
        return df
    df["Trạng thái"] = df["confidence"].astype(str).str.upper().map(
        {
            "LOW": "Chưa xác minh",
            "MEDIUM": "Đã nhập thủ công",
            "HIGH": "Đã xác minh",
        }
    ).fillna("Chưa xác minh")
    return rename_for_display(
        df,
        {
            "brand_name": "Brand",
            "affiliate_program_url": "Affiliate program URL",
            "terms_url": "Terms URL",
            "payout_source": "Nguồn payout",
            "policy_source": "Nguồn policy",
            "last_checked": "Lần kiểm tra cuối",
            "confidence": "Độ tin cậy",
            "Trạng thái": "Trạng thái",
        },
    )


def render_reports(offers_df: pd.DataFrame, market_df: pd.DataFrame, roi_df: pd.DataFrame) -> None:
    st.markdown("### 1. Top offer nên test")
    top = recommended_to_test(offers_df).copy()
    if not top.empty:
        top["Lý do"] = top.apply(test_reason, axis=1)
    st.dataframe(
        rename_for_display(
            top,
            {
                "brand_name": "Brand",
                "niche": "Niche",
                "total_score": "Score",
                "estimated_roi": "ROI dự kiến",
                "risk_level": "Risk",
                "data_confidence": "Độ tin cậy",
                "recommended_channels": "Kênh đề xuất",
                "Lý do": "Lý do",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 2. Offer rủi ro chính sách")
    policy = offers_df[offers_df["policy_notes"].astype(str).str.strip() != ""].copy()
    policy["Hành động đề xuất"] = policy.apply(
        lambda row: "Không tạo ads" if row.get("compliance_status") == "BLOCKED" else "Kiểm tra policy thật và dùng landing page review",
        axis=1,
    )
    st.dataframe(
        rename_for_display(
            policy,
            {
                "brand_name": "Brand",
                "policy_notes": "Vấn đề",
                "risk_level": "Mức rủi ro",
                "data_source_note": "Ghi chú dữ liệu",
                "Hành động đề xuất": "Hành động đề xuất",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 3. Niche tiềm năng")
    st.dataframe(
        rename_for_display(
            market_df,
            {
                "niche": "Niche",
                "trend_status": "Trend",
                "estimated_competition": "Competition",
                "estimated_cpc": "CPC dự kiến",
                "market_notes": "Ghi chú",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 4. Campaign nên hành động")
    action = roi_df[roi_df["decision"].astype(str).isin(["PAUSE", "OPTIMIZE", "SCALE"])].copy()
    st.dataframe(
        rename_for_display(
            action,
            {
                "campaign": "Campaign",
                "ROI": "ROI",
                "profit": "Profit",
                "decision": "Quyết định",
                "decision_reason": "Lý do",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 5. Việc cần làm tiếp theo")
    for item in [
        "Kiểm tra affiliate policy thật.",
        "Tạo landing page review.",
        "Upload CSV thủ công lên Ads Editor.",
        "Test ngân sách nhỏ.",
        "Theo dõi ROI sau 3-5 ngày.",
    ]:
        st.write(f"- {item}")

    st.markdown("### 6. Việc cần xác minh trước khi chạy ads thật")
    for item in [
        "Đã kiểm tra affiliate terms chưa?",
        "Đã kiểm tra trademark bidding chưa?",
        "Đã kiểm tra direct linking chưa?",
        "Đã kiểm tra payout thật chưa?",
        "Đã kiểm tra cookie duration thật chưa?",
        "Đã thay Final URL local bằng URL landing page thật trên domain của bạn chưa?",
    ]:
        st.write(f"- {item}")


st.set_page_config(page_title="AI Affiliate Intelligence Platform", layout="wide")
inject_dashboard_css()
st.title("AI Affiliate Intelligence Platform")
st.caption("Nền tảng tìm offer, phân tích chính sách, tạo CSV quảng cáo và theo dõi ROI.")
st.warning("Dữ liệu hiện tại là dữ liệu mẫu/rule-based. Cần kiểm tra affiliate policy và số liệu thật trước khi chạy ngân sách.")

sidebar_page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Review Queue",
        "Content Approval",
        "Social Distribution",
        "Phân phối xã hội",
        "Post Deploy Kit",
        "SEO System",
        "Performance Intelligence",
        "Reports",
    ],
    index=0,
)
st.sidebar.caption("Local-safe workflow. No deploy and no social auto-posting without approval.")

offers = read_csv(settings.offer_scores_file)
keywords = read_csv(settings.keywords_file)
keyword_opportunities = read_csv(settings.data_dir / "keyword_opportunities.csv")
keyword_summary = read_csv(settings.data_dir / "keyword_intelligence_summary.csv")
keyword_priority_plan = read_csv(settings.data_dir / "keyword_priority_plan.csv")
market = read_csv(settings.market_insights_file)
google_ads = read_csv(settings.google_ads_file)
bing_ads = read_csv(settings.bing_ads_file)
roi = read_csv(settings.roi_report_file)
landing_index = read_csv(settings.data_dir / "landing_pages_index.csv")
angles = read_csv(settings.data_dir / "ai_angles.csv")
data_sources = read_csv(settings.data_sources_file)
affiliate_links = load_affiliate_links()
review_queue = load_review_queue()
social_posts = read_social_post_report()
social_queue = load_queue()
pending_review_count = 0
if not review_queue.empty and "status" in review_queue.columns:
    pending_review_count = int(review_queue["status"].astype(str).isin(["Pending Review", "Need Edit", "Approved"]).sum())
scheduled_social_count = 0
if not social_queue.empty and "status" in social_queue.columns:
    scheduled_social_count = int(social_queue["status"].astype(str).isin(["Scheduled", "Approved"]).sum())

if sidebar_page == "Social Distribution":
    render_social_distribution_page(review_queue)
    st.stop()
elif sidebar_page == "Phân phối xã hội":
    render_manual_social_distribution_page()
    st.stop()
elif sidebar_page == "Post Deploy Kit":
    render_post_deploy_page()
    st.stop()
elif sidebar_page == "SEO System":
    render_seo_system_page()
    st.stop()
elif sidebar_page == "Performance Intelligence":
    render_performance_intelligence_page()
    st.stop()
elif sidebar_page == "Review Queue":
    st.info("Review Queue is available in the Content Review tab below. Use the sidebar Social Distribution item for the dedicated social workflow.")
elif sidebar_page == "Content Approval":
    st.info("Content Approval is available in the Content Review tab below. Existing approval workflow is unchanged.")
elif sidebar_page == "Reports":
    st.info("Reports are available in the Reports tab below. Existing report workflow is unchanged.")

metric_cards(offers)

tabs = st.tabs(
    [
        "Xếp hạng offer",
        "Chi tiết offer",
        "Phân tích từ khóa",
        "Tạo quảng cáo",
        "Landing Page",
        "Dự phóng lợi nhuận",
        "Theo dõi ROI",
        "Nhập offer tự động",
        "Nguồn dữ liệu",
        "Báo cáo",
        "Affiliate Links",
        "Affiliate OS",
        f"Duyệt nội dung ({pending_review_count}) / Content Review",
        "SEO Programmatic Pages",
        "Affiliate Tracking",
        f"Social Distribution ({scheduled_social_count})",
        "Phân phối xã hội",
    ]
)

with tabs[0]:
    st.subheader("Xếp hạng offer")
    if offers.empty:
        st.warning("Chưa có dữ liệu. Hãy chạy `python main.py` trước.")
    else:
        recommended = recommended_to_test(offers)
        st.markdown("### Offer nên test trước")
        if recommended.empty:
            st.info("Chưa có offer đủ điều kiện test trước.")
        else:
            rec_cols = st.columns(min(3, len(recommended)))
            for idx, (_, rec) in enumerate(recommended.iterrows()):
                with rec_cols[idx % len(rec_cols)]:
                    offer_card(rec, test_first=True)

        st.markdown("### Bộ lọc")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        niche = c1.multiselect("Ngách", sorted(offers["niche"].unique()))
        grade = c2.multiselect("Xếp hạng", sorted(offers["grade"].unique()))
        risk = c3.multiselect("Rủi ro", sorted(offers["risk_level"].unique()), format_func=risk_label)
        trend = c4.multiselect("Xu hướng", sorted(offers["trend"].unique()), format_func=trend_label)
        competition = c5.multiselect("Mức cạnh tranh", sorted(offers["competition"].unique()), format_func=competition_label)
        channel_options = sorted(
            {
                channel.strip()
                for channels in offers["recommended_channels"].astype(str)
                for channel in channels.split(",")
                if channel.strip()
            }
        )
        channel = c6.multiselect("Kênh traffic", channel_options)

        df = offers.copy()
        if niche:
            df = df[df["niche"].isin(niche)]
        if grade:
            df = df[df["grade"].isin(grade)]
        if risk:
            df = df[df["risk_level"].isin(risk)]
        if trend:
            df = df[df["trend"].isin(trend)]
        if competition:
            df = df[df["competition"].isin(competition)]
        if channel:
            df = df[df["recommended_channels"].astype(str).apply(lambda value: any(item in value for item in channel))]

        view = st.radio("Kiểu hiển thị", ["Card", "Bảng"], horizontal=True)
        if view == "Card":
            for start in range(0, len(df), 3):
                cols = st.columns(3)
                for offset, (_, row) in enumerate(df.iloc[start : start + 3].iterrows()):
                    with cols[offset]:
                        offer_card(row)
        else:
            st.dataframe(display_offer_table(df), use_container_width=True, hide_index=True)

        st.markdown("### Cảnh báo chính sách")
        st.warning(
            "Nếu policy có No PPC, No Google Ads, No Bing Ads, No direct linking hoặc No trademark bidding "
            "thì phải kiểm tra kỹ trước khi upload. Offer bị BLOCKED sẽ không được tạo quảng cáo."
        )
        st.dataframe(
            rename_for_display(
                df,
                {
                    "brand_name": "Tên thương hiệu",
                    "google_ads_policy": "Google Ads",
                    "bing_ads_policy": "Bing Ads",
                    "policy_notes": "Cảnh báo",
                    "data_confidence": "Độ tin cậy dữ liệu",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )

with tabs[1]:
    st.subheader("Chi tiết offer")
    if not offers.empty:
        selected = st.selectbox("Chọn offer", offers["brand_name"].tolist())
        row = offers[offers["brand_name"] == selected].iloc[0]
        cols = st.columns(5)
        cols[0].metric("Điểm tổng", f"{row['total_score']}/100")
        cols[1].metric("Xếp hạng", row["grade"])
        cols[2].metric("Rủi ro", risk_label(row["risk_level"]))
        cols[3].metric("ROI dự kiến", f"{row['estimated_roi']}%")
        cols[4].metric("Độ tin cậy", row.get("data_confidence", "LOW"))
        st.markdown(f"Trạng thái chính sách: {status_badge(str(row['compliance_status']))}", unsafe_allow_html=True)
        st.write(row["recommendation"])
        st.info(row["policy_notes"])
        st.warning(str(row.get("data_source_note", "Dữ liệu chưa xác minh.")))

        st.markdown("### Checklist kiểm tra thực tế")
        checklist = pd.DataFrame(
            [
                {"Việc cần kiểm tra": "Đã kiểm tra affiliate terms chưa?", "Trạng thái": "Chưa xác minh" if row.get("data_confidence") == "LOW" else "Cần review lại"},
                {"Việc cần kiểm tra": "Đã kiểm tra trademark bidding chưa?", "Trạng thái": "Chưa xác minh"},
                {"Việc cần kiểm tra": "Đã kiểm tra direct linking chưa?", "Trạng thái": "Chưa xác minh"},
                {"Việc cần kiểm tra": "Đã kiểm tra payout thật chưa?", "Trạng thái": "Chưa xác minh"},
                {"Việc cần kiểm tra": "Đã kiểm tra cookie duration thật chưa?", "Trạng thái": "Chưa xác minh"},
            ]
        )
        st.dataframe(checklist, use_container_width=True, hide_index=True)

        st.markdown("### Vì sao nên / không nên chạy?")
        col_good, col_risk, col_strategy = st.columns(3)
        with col_good:
            st.markdown("**Vì sao đáng test**")
            for item in build_positive_reasons(row):
                st.write(f"- {item}")
        with col_risk:
            st.markdown("**Rủi ro cần chú ý**")
            for item in build_risk_reasons(row):
                st.write(f"- {item}")
        with col_strategy:
            st.markdown("**Chiến lược đề xuất**")
            for item in build_strategy(row):
                st.write(f"- {item}")

        st.markdown("### Breakdown điểm")
        breakdown = pd.DataFrame(
            [
                {"Yếu tố": "Kinh tế/hoa hồng", "Điểm": row.get("economics_score", 0)},
                {"Yếu tố": "Chính sách", "Điểm": row.get("policy_score", 0)},
                {"Yếu tố": "Độ tin cậy vendor", "Điểm": row.get("trust_score", 0)},
                {"Yếu tố": "Buyer Intent", "Điểm": row.get("buyer_intent_score", 0)},
                {"Yếu tố": "Mức cạnh tranh", "Điểm": row.get("competition_score", 0)},
                {"Yếu tố": "Xu hướng", "Điểm": row.get("trend_score", 0)},
                {"Yếu tố": "CPC", "Điểm": row.get("cpc_score", 0)},
                {"Yếu tố": "ROI", "Điểm": row.get("roi_score", 0)},
                {"Yếu tố": "Penalty", "Điểm": -float(row.get("penalty_score", 0) or 0)},
            ]
        )
        st.bar_chart(breakdown.set_index("Yếu tố"))
        st.dataframe(breakdown, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Phân tích từ khóa")
    if not keyword_summary.empty:
        row = keyword_summary.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total keywords", int(row.get("total_keywords", 0) or 0))
        c2.metric("Unique keywords", int(row.get("total_unique_keywords", 0) or 0))
        c3.metric("Duplicate removed", int(row.get("duplicate_removed", 0) or 0))
        c4.metric("High priority", int(row.get("high_opportunity_keywords", 0) or 0))
    if not keyword_priority_plan.empty:
        st.markdown("### Top 30 keyword priority plan")
        st.dataframe(
            rename_for_display(
                keyword_priority_plan,
                {
                    "priority_rank": "Rank",
                    "keyword": "Keyword",
                    "keyword_group": "Nhóm chiến lược",
                    "page_type": "Loại page",
                    "seo_priority_score": "SEO priority",
                    "suggested_slug": "Slug đề xuất",
                    "target_page_title": "Title đề xuất",
                    "reason": "Lý do",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )
    if not keyword_opportunities.empty:
        with st.expander("Keyword opportunities đầy đủ", expanded=False):
            st.dataframe(keyword_opportunities, use_container_width=True, hide_index=True)
    if not keywords.empty:
        brand = st.selectbox("Offer", sorted(keywords["brand_name"].unique()), key="kw_offer")
        st.dataframe(
            rename_for_display(
                keywords[keywords["brand_name"] == brand],
                {
                    "brand_name": "Tên thương hiệu",
                    "niche": "Ngách",
                    "keyword_group": "Nhóm keyword",
                    "keyword": "Keyword",
                    "intent_score": "Điểm intent",
                    "competition_level": "Mức cạnh tranh",
                    "estimated_cpc": "CPC dự kiến",
                    "match_type": "Match type",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )

with tabs[3]:
    st.subheader("Tạo quảng cáo")
    st.warning("CSV đang ở trạng thái PAUSED, cần kiểm tra trước khi upload. Hệ thống không tự chạy ads và không tự tiêu tiền.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Google Ads CSV**")
        st.dataframe(google_ads, use_container_width=True, hide_index=True)
        if not google_ads.empty:
            st.download_button("Tải CSV Google Ads", google_ads.to_csv(index=False).encode("utf-8-sig"), file_name="ads_google.csv")
    with c2:
        st.markdown("**Bing/Microsoft Ads CSV**")
        st.dataframe(bing_ads, use_container_width=True, hide_index=True)
        if not bing_ads.empty:
            st.download_button("Tải CSV Bing Ads", bing_ads.to_csv(index=False).encode("utf-8-sig"), file_name="ads_bing.csv")

with tabs[4]:
    st.subheader("Landing Page")
    st.write("Landing Page có affiliate disclosure và cảnh báo policy. Trước khi publish cần thêm Privacy Policy, Terms và Contact thật.")
    if settings.base_site_url:
        st.success(f"BASE_SITE_URL đang bật: {settings.base_site_url}. Ads CSV sẽ ưu tiên URL domain thật.")
    else:
        st.warning("Chưa có BASE_SITE_URL trong .env. Ads CSV đang dùng link local landing page, chưa nên chạy ads thật.")
    c1, c2 = st.columns(2)
    if c1.button("Build website deploy folder"):
        result = build_site_output(landing_index, settings.base_site_url, offers)
        st.success(f"Đã build {result['pages']} landing page vào {result['site_output']}")
    if c2.button("Mở thư mục site_output"):
        st.info(f"Thư mục deploy: {settings.site_output_dir.resolve()}")
    st.markdown(
        """
        **Hướng dẫn deploy**
        - Upload toàn bộ thư mục `site_output/` lên Netlify hoặc Vercel.
        - Gắn domain thật vào project.
        - Thêm `BASE_SITE_URL=https://yourdomain.com` vào `.env`.
        - Chạy lại `python main.py` để Ads CSV dùng URL thật làm Final URL.
        """
    )
    st.markdown("### Checklist trước khi deploy/chạy ads")
    checklist = pd.DataFrame(
        [
            {"Hạng mục": "Domain thật đã cấu hình chưa?", "Trạng thái": "Đã cấu hình" if bool(settings.base_site_url) else "Chưa cấu hình"},
            {"Hạng mục": "Có affiliate disclosure chưa?", "Trạng thái": "Có"},
            {"Hạng mục": "Có privacy policy chưa?", "Trạng thái": "Có" if (settings.site_output_dir / "privacy-policy" / "index.html").exists() else "Chưa build"},
            {"Hạng mục": "Có terms chưa?", "Trạng thái": "Có" if (settings.site_output_dir / "terms" / "index.html").exists() else "Chưa build"},
            {"Hạng mục": "Có contact chưa?", "Trạng thái": "Có" if (settings.site_output_dir / "contact" / "index.html").exists() else "Chưa build"},
            {"Hạng mục": "Có sitemap chưa?", "Trạng thái": "Có" if (settings.site_output_dir / "sitemap.xml").exists() else "Chưa build"},
            {"Hạng mục": "Có robots.txt chưa?", "Trạng thái": "Có" if (settings.site_output_dir / "robots.txt").exists() else "Chưa build"},
        ]
    )
    st.dataframe(checklist, use_container_width=True, hide_index=True)
    if not landing_index.empty and "landing_page_url" in landing_index.columns:
        for _, row in landing_index.iterrows():
            st.markdown(f"- [{row.get('brand_name', '')}]({row.get('landing_page_url', '')})")
    st.dataframe(
        rename_for_display(
            landing_index,
            {
                "brand_name": "Tên thương hiệu",
                "landing_page": "File HTML",
                "landing_page_url": "Link preview",
                "status": "Trạng thái",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

with tabs[5]:
    st.subheader("Dự phóng lợi nhuận")
    if not offers.empty:
        brand = st.selectbox("Offer", offers["brand_name"].tolist(), key="profit_offer")
        row = offers[offers["brand_name"] == brand].iloc[0].to_dict()
        c1, c2 = st.columns(2)
        budget = c1.number_input("Ngân sách/ngày", min_value=1.0, value=25.0, step=5.0)
        cpc = c2.number_input("CPC gốc", min_value=0.01, value=float(row.get("estimated_cpc") or 3.0), step=0.1)
        scenarios = simulate_scenarios(row, daily_budget=budget, base_cpc=cpc)
        st.markdown("### 3 kịch bản ROI")
        st.dataframe(
            scenarios.rename(
                columns={
                    "scenario": "Kịch bản",
                    "Conversion Rate": "Tỷ lệ chuyển đổi",
                    "ROI": "ROI",
                    "Profit": "Lợi nhuận",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        normal = scenarios[scenarios["scenario"] == "Normal"].iloc[0].to_dict()
        if float(normal.get("ROI") or 0) < 0:
            st.error("ROI âm: Không nên scale, chỉ test nhỏ hoặc đổi keyword.")
        elif float(normal.get("ROI") or 0) < 30:
            st.warning("ROI dương thấp: Theo dõi thêm.")
        else:
            st.success("ROI cao: Có thể tăng ngân sách từ từ.")

        st.markdown("### Tùy chỉnh thủ công")
        c1, c2, c3, c4 = st.columns(4)
        budget_manual = c1.number_input("Ngân sách/ngày ", min_value=1.0, value=25.0, step=5.0)
        cpc_manual = c2.number_input("CPC dự kiến", min_value=0.01, value=float(row.get("estimated_cpc") or 3.0), step=0.1)
        ctr = c3.number_input("CTR dự kiến", min_value=0.001, value=0.045, step=0.005, format="%.3f")
        conv = c4.number_input("Tỷ lệ chuyển đổi dự kiến", min_value=0.001, value=0.025, step=0.005, format="%.3f")
        result = simulate_offer_profit(row, daily_budget=budget_manual, ctr=ctr, conversion_rate=conv, cpc=cpc_manual)
        st.dataframe(pd.DataFrame([translate_profit_result(result)]), use_container_width=True, hide_index=True)

with tabs[6]:
    st.subheader("Theo dõi ROI")
    st.write("Nhập/export số liệu campaign vào `data/campaign_results.csv`, rồi chạy lại `python main.py`.")
    st.dataframe(
        rename_for_display(
            roi,
            {
                "campaign": "Campaign",
                "offer_name": "Offer",
                "CTR": "CTR",
                "CPC": "CPC",
                "CPA": "CPA",
                "EPC": "EPC",
                "ROI": "ROI",
                "profit": "Profit",
                "decision": "Quyết định",
                "decision_reason": "Lý do",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )

with tabs[7]:
    st.subheader("Nhập offer tự động")
    st.info(
        "Bản này dùng rule-based, không scrape mạnh, không bypass login và không lấy dữ liệu sau paywall. "
        "Nếu thiếu dữ liệu, hệ thống sẽ để UNKNOWN/NEED_REVIEW và LOW confidence."
    )

    with st.form("single_offer_form"):
        st.markdown("### Nhập một offer")
        c1, c2 = st.columns(2)
        brand_name = c1.text_input("Brand name")
        network = c2.selectbox("Network", ["PartnerStack", "Impact", "CJ", "ShareASale", "Digistore24", "ClickBank", "Other"])
        affiliate_program_url = st.text_input("Affiliate program URL")
        affiliate_url = st.text_input("Affiliate link")
        terms_url = st.text_input("Terms URL")
        c1, c2, c3 = st.columns(3)
        commission = c1.text_input("Commission", placeholder="VD: 30% recurring hoặc $50")
        cookie_days = c2.text_input("Cookie days", placeholder="VD: 30")
        country_allowed = c3.text_input("Country allowed", value="UNKNOWN")
        manual_note = st.text_area("Ghi chú thủ công")
        submitted = st.form_submit_button("Lưu offer")

    if submitted:
        record = build_offer_record(
            brand_name=brand_name,
            affiliate_program_url=affiliate_program_url,
            affiliate_url=affiliate_url,
            terms_url=terms_url,
            network=network,
            commission=commission,
            cookie_days=cookie_days,
            country_allowed=country_allowed,
            manual_note=manual_note,
        )
        errors = validate_required_fields(record)
        if errors:
            for error in errors:
                st.error(error)
        else:
            save_user_offer(record)
            st.success("Đã lưu offer vào data/user_offers.csv. Hãy bấm Phân tích offer để đưa vào dashboard.")
            st.warning("Chưa xác minh chính sách. Không nên chạy ads thật cho đến khi kiểm tra terms.")
            st.dataframe(pd.DataFrame([record]), use_container_width=True, hide_index=True)

    st.markdown("### Dán nhiều link")
    bulk_links = st.text_area(
        "Mỗi dòng một affiliate/program URL",
        placeholder="https://example.com/affiliate\nhttps://example.com/partners\nhttps://partnerstack.com/xxx",
        key="bulk_offer_links",
    )
    bulk_network = st.selectbox("Network cho các link này", ["Other", "PartnerStack", "Impact", "CJ", "ShareASale", "Digistore24", "ClickBank"], key="bulk_network")
    bulk_note = st.text_input("Ghi chú cho batch", key="bulk_note")
    if st.button("Lưu nhiều link"):
        saved = save_many_from_links(bulk_links, network=bulk_network, manual_note=bulk_note)
        st.success(f"Đã lưu {len(saved)} offer user trong data/user_offers.csv.")
        st.warning("Các offer mới có LOW confidence và NEED_REVIEW policy cho đến khi bạn kiểm tra terms.")

    st.markdown("### Thao tác tự động")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Phân tích offer"):
        run_pipeline()
        st.success("Đã phân tích lại offer và cập nhật dashboard data.")
    if c2.button("Tạo landing page"):
        run_pipeline()
        st.success("Đã tạo/cập nhật landing page trong landing_pages/output.")
    if c3.button("Tạo keyword"):
        run_pipeline()
        st.success("Đã tạo/cập nhật data/keywords.csv.")
    if c4.button("Tạo ads CSV"):
        run_pipeline()
        st.success("Đã tạo/cập nhật data/ads_google.csv và data/ads_bing.csv.")

    st.markdown("### Offer user đã nhập")
    st.dataframe(load_user_offers(), use_container_width=True, hide_index=True)

with tabs[8]:
    st.subheader("Nguồn dữ liệu")
    st.info("LOW = Chưa xác minh, MEDIUM = Đã nhập thủ công, HIGH = Đã xác minh bằng nguồn/API.")
    st.dataframe(display_data_sources(data_sources), use_container_width=True, hide_index=True)

with tabs[9]:
    st.subheader("Báo cáo Affiliate AI")
    render_reports(offers, market, roi)
    if not angles.empty:
        st.subheader("Góc nội dung AI")
        st.dataframe(angles, use_container_width=True, hide_index=True)

with tabs[11]:
    st.subheader("Affiliate OS")
    st.warning("Review before publishing. Do not spam. This tool only creates drafts and does not auto-post or spend ad budget.")
    skills_df = pd.DataFrame(list_skills())
    st.markdown("### Skill commands")
    st.dataframe(skills_df, use_container_width=True, hide_index=True)

    commands = skills_df["command"].tolist()
    selected_command = st.selectbox("Choose skill", commands)
    c1, c2 = st.columns(2)
    product_name = c1.text_input("Product / tool name", value="Gamma")
    main_keyword = c2.text_input("Main keyword", value="Gamma review")
    target_audience = c1.text_input("Target audience", value="small business owners")
    competitors = c2.text_input("Competitors", value="Canva, Webflow, Notion AI")
    extra_inputs = st.text_area(
        "Extra inputs / content / notes",
        placeholder="Paste affiliate terms, article draft, analytics notes, target prompt, or campaign data here.",
        height=180,
    )
    c1, c2, c3 = st.columns(3)
    affiliate_commission = c1.text_input("Affiliate commission", value="30")
    cookie_duration = c2.text_input("Cookie duration", value="30")
    product_price = c3.text_input("Product price", value="50")
    competition_level = st.selectbox("Competition level", ["Low", "Medium", "High"], index=1)
    status = st.selectbox("Status", ["Draft", "Approved", "Published"], index=0)

    inputs = {
        "product_name": product_name,
        "main_keyword": main_keyword,
        "target_audience": target_audience,
        "competitors": competitors,
        "content": extra_inputs,
        "affiliate_commission": affiliate_commission,
        "cookie_duration": cookie_duration,
        "product_price": product_price,
        "competition_level": competition_level,
    }
    if st.button("Run skill"):
        result = run_skill(selected_command, inputs)
        st.session_state["affiliate_os_output"] = result["output"]
        st.session_state["affiliate_os_command"] = selected_command

    output = st.session_state.get("affiliate_os_output", "")
    st.markdown("### Output preview")
    edited_output = st.text_area("Draft output", value=output, height=420)
    st.caption("Copy from this box manually after review. No auto-posting is connected.")
    if st.button("Save draft"):
        path = save_draft(st.session_state.get("affiliate_os_command", selected_command), inputs, edited_output, status=status)
        st.success(f"Saved draft to {path}")

with tabs[10]:
    st.subheader("Affiliate Links")
    st.info("Nếu `approved=false` hoặc chưa có affiliate_url, nút CTA trên website sẽ dùng official_url và hiện ghi chú affiliate link pending approval.")
    with st.form("affiliate_link_form"):
        c1, c2 = st.columns(2)
        brand = c1.text_input("Brand")
        slug = c2.text_input("Slug")
        official_url = st.text_input("Official URL")
        affiliate_url = st.text_input("Affiliate URL")
        c1, c2, c3 = st.columns(3)
        approved = c1.checkbox("Approved")
        network = c2.text_input("Network", value="Other")
        status = c3.text_input("Status", value="pending_approval")
        commission_note = st.text_input("Commission note", value="Affiliate link pending approval.")
        if st.form_submit_button("Lưu affiliate link"):
            upsert_affiliate_link(
                {
                    "brand": brand,
                    "slug": slug,
                    "official_url": official_url,
                    "affiliate_url": affiliate_url,
                    "approved": approved,
                    "network": network,
                    "status": status,
                    "commission_note": commission_note,
                }
            )
            st.success("Đã lưu vào data/affiliate_links.csv. Chạy lại python main.py để build site_output dùng link mới.")
    edited_links = st.data_editor(affiliate_links, use_container_width=True, hide_index=True, num_rows="dynamic")
    if st.button("Lưu bảng affiliate_links.csv"):
        save_affiliate_links(edited_links)
        st.success("Đã lưu bảng affiliate_links.csv.")

with tabs[12]:
    st.subheader("Duyệt nội dung")
    st.warning("Bot chỉ tạo nháp. Không tự đăng. Người dùng phải duyệt trước khi publish hoặc copy sang kênh khác.")

    drafts = load_review_queue()

    st.markdown("### Tạo nháp")
    with st.form("content_draft_form"):
        c1, c2 = st.columns(2)
        topic = c1.text_input("Topic", value="Gamma vs Canva")
        main_keyword = c2.text_input("Main keyword", value="Gamma vs Canva")
        target_tool = c1.text_input("Target tool", value="Gamma")
        target_audience = c2.text_input("Target audience", value="người làm affiliate và small business")
        content_type = c1.selectbox(
            "Content type",
            ["Review page", "Comparison page", "LinkedIn post", "Facebook post", "Medium article", "X thread", "Telegram post", "TikTok script", "FAQ page", "Blog article"],
        )
        tone = c2.selectbox("Tone", ["gần gũi", "chuyên nghiệp", "kỹ thuật", "storytelling", "bán hàng nhẹ"])
        submitted = st.form_submit_button("Tạo nháp")
    if submitted:
        content = generate_draft_content(topic, main_keyword, target_tool, content_type, target_audience, tone)
        record = create_draft(
            content_type=content_type,
            target_channel=content_type,
            title=topic,
            slug=draft_slugify(topic),
            topic=topic,
            draft_content=content,
            status="Pending Review",
            notes=f"Generated from dashboard. Tone: {tone}.",
        )
        st.success(f"Đã tạo nháp {record['draft_id']} ở trạng thái Đang chờ duyệt.")
        drafts = load_review_queue()

    st.markdown("### Tạo multichannel pack")
    c1, c2, c3 = st.columns(3)
    pack_topic = c1.text_input("Pack topic", value="Best AI presentation tools", key="pack_topic")
    pack_tool = c2.text_input("Tool", value="Gamma", key="pack_tool")
    pack_keyword = c3.text_input("Keyword", value="best AI presentation tools", key="pack_keyword")
    if st.button("Tạo pack nhiều kênh"):
        records = generate_multichannel_pack(pack_topic, pack_tool, pack_keyword)
        st.success(f"Đã tạo {len(records)} nháp cho nhiều kênh.")
        drafts = load_review_queue()

    st.markdown("### AEO Gap Ideas")
    c1, c2 = st.columns(2)
    idea_tool = c1.text_input("Tool cho AEO ideas", value="Gamma", key="idea_tool")
    idea_use_case = c2.text_input("Use case", value="small business", key="idea_use_case")
    ideas = generate_aeo_ideas(idea_tool, idea_use_case)
    selected_ideas = st.multiselect("Chọn ideas để lưu thành draft", [idea["title"] for idea in ideas])
    if st.button("Lưu selected AEO ideas"):
        for idea in ideas:
            if idea["title"] in selected_ideas:
                content = generate_draft_content(idea["topic"], idea["title"], idea_tool, "Blog article", "người tìm kiếm AI/SaaS", "chuyên nghiệp")
                create_draft(
                    content_type="Blog article",
                    target_channel="Website",
                    title=idea["title"],
                    slug=idea["slug"],
                    topic=idea["topic"],
                    draft_content=content,
                    status="Pending Review",
                    notes="AEO gap idea generated from dashboard.",
                )
        st.success(f"Đã lưu {len(selected_ideas)} AEO ideas vào Draft Queue.")
        drafts = load_review_queue()

    st.markdown("### Draft Queue")
    if drafts.empty:
        st.info("Chưa có draft nào. Hãy tạo nháp trước.")
    else:
        c1, c2 = st.columns(2)
        status_filter = c1.selectbox("Lọc theo trạng thái", ["All", "Pending Review", "Approved", "Need Edit", "Rejected", "Published"])
        channels = sorted([x for x in drafts["target_channel"].astype(str).unique().tolist() if x])
        channel_filter = c2.selectbox("Lọc theo channel", ["All"] + channels)
        filtered = drafts.copy()
        if status_filter != "All":
            filtered = filtered[filtered["status"] == status_filter]
        if channel_filter != "All":
            filtered = filtered[filtered["target_channel"] == channel_filter]
        queue_view = filtered.copy()
        queue_view["keyword"] = queue_view["topic"]
        st.dataframe(queue_view[["draft_id", "title", "keyword", "status", "created_at", "content_type"]], use_container_width=True, hide_index=True)

        selected_id = st.selectbox("Chọn draft để preview / Content Review", filtered["draft_id"].astype(str).tolist() if not filtered.empty else [])
        if selected_id:
            row = drafts[drafts["draft_id"].astype(str) == selected_id].iloc[0].to_dict()
            st.markdown(f"#### Preview: {row.get('title', '')}")
            edited_title = st.text_input("Title", value=str(row.get("title", "")), key=f"title_{selected_id}")
            edited_slug = st.text_input("Slug", value=str(row.get("slug", "")), key=f"slug_{selected_id}")
            edited_notes = st.text_area("Notes", value=str(row.get("notes", "")), key=f"notes_{selected_id}", height=90)
            edited_content = st.text_area("Draft content", value=str(row.get("draft_content", "")), key=f"content_{selected_id}", height=360)
            parts = extract_review_parts(edited_content)
            p1, p2 = st.columns(2)
            with p1.expander("SEO meta", expanded=True):
                st.text_area("SEO meta preview", value=parts["seo_meta"], height=120, disabled=True, key=f"seo_{selected_id}")
            with p2.expander("FAQ", expanded=True):
                st.text_area("FAQ preview", value=parts["faq"], height=120, disabled=True, key=f"faq_{selected_id}")
            p3, p4, p5 = st.columns(3)
            with p3.expander("CTA", expanded=False):
                st.text_area("CTA preview", value=parts["cta"], height=100, disabled=True, key=f"cta_{selected_id}")
            with p4.expander("Internal links", expanded=False):
                st.text_area("Internal links preview", value=parts["internal_links"], height=100, disabled=True, key=f"links_{selected_id}")
            with p5.expander("Affiliate disclosure", expanded=False):
                st.text_area("Affiliate disclosure preview", value=parts["affiliate_disclosure"], height=100, disabled=True, key=f"disclosure_{selected_id}")
            ok_to_approve, issues = can_approve(edited_content, edited_title)
            if issues:
                st.warning("Compliance check:")
                for issue in issues:
                    st.write(f"- {issue}")
            else:
                st.success("Compliance check không thấy lỗi lớn.")

            c1, c2, c3, c4 = st.columns(4)
            if c1.button("Lưu chỉnh sửa"):
                update_draft(selected_id, title=edited_title, slug=edited_slug, notes=edited_notes, draft_content=edited_content)
                st.success("Đã lưu chỉnh sửa.")
                drafts = load_review_queue()
            if c2.button("Approve / Duyệt"):
                if not ok_to_approve:
                    st.error("Có lỗi severe. Hãy chỉnh sửa trước khi duyệt.")
                else:
                    update_draft(selected_id, status="Approved", title=edited_title, slug=edited_slug, notes=edited_notes, draft_content=edited_content)
                    st.success("Đã duyệt nội dung.")
                    drafts = load_review_queue()
            if c3.button("Reject / Từ chối"):
                update_draft(selected_id, status="Rejected", notes=edited_notes)
                st.success("Đã chuyển sang Từ chối.")
                drafts = load_review_queue()
            if c4.button("Need Edit / Cần chỉnh sửa"):
                update_draft(selected_id, status="Need Edit", notes=edited_notes)
                st.success("Đã chuyển sang Need Edit để chỉnh sửa.")
                drafts = load_review_queue()

            c1, c2, c3, c4 = st.columns(4)
            c1.download_button("Sao chép nội dung", data=edited_content, file_name=f"{edited_slug or selected_id}.txt", mime="text/plain")
            c2.download_button("Export Markdown", data=export_markdown({**row, "title": edited_title, "draft_content": edited_content}), file_name=f"{edited_slug or selected_id}.md", mime="text/markdown")
            c3.download_button("Export HTML draft", data=export_html({**row, "title": edited_title, "draft_content": edited_content}), file_name=f"{edited_slug or selected_id}.html", mime="text/html")
            c4.download_button("Copy title", data=edited_title, file_name=f"{edited_slug or selected_id}-title.txt", mime="text/plain")
            st.download_button("Copy URL", data=str(row.get("target_url", "")), file_name=f"{edited_slug or selected_id}-url.txt", mime="text/plain")

            if row.get("status") in {"Approved", "Published"}:
                overwrite = st.checkbox("Cho phép ghi đè nếu slug đã tồn tại", value=False)
                if st.button("Publish to Site"):
                    update_draft(selected_id, title=edited_title, slug=edited_slug, notes=edited_notes, draft_content=edited_content)
                    ok, message = publish_static_draft(selected_id, overwrite=overwrite)
                    if ok:
                        st.success(f"Published to site: {message}")
                    else:
                        st.error(message)
                    drafts = load_review_queue()
                if st.button("Tạo off-page drafts từ trang đã duyệt"):
                    records = generate_offpage_pack({**row, "title": edited_title, "draft_content": edited_content})
                    st.success(f"Đã tạo {len(records)} off-page drafts.")
                    drafts = load_review_queue()

            if st.button("Đánh dấu đã đăng"):
                if row.get("content_type") in {"Review page", "Comparison page", "FAQ page", "Blog article", "Website article"}:
                    if row.get("status") != "Approved":
                        st.error("Website drafts must be Approved first, then use Publish to Site so the file and sitemap are created.")
                    else:
                        update_draft(selected_id, title=edited_title, slug=edited_slug, notes=edited_notes, draft_content=edited_content)
                        ok, message = publish_static_draft(selected_id, overwrite=True)
                        if ok:
                            st.success(f"Published to site: {message}")
                        else:
                            st.error(message)
                else:
                    manual_url = str(row.get("target_url", "")).strip()
                    update_draft(selected_id, status="Published", target_url=manual_url, notes=f"{edited_notes} | Marked published manually")
                    st.success("Đã đánh dấu đã đăng.")
                drafts = load_review_queue()

    st.markdown("### Backup / Export CSV")
    all_csv = drafts.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Export all drafts CSV", data=all_csv, file_name="content_drafts_all.csv", mime="text/csv")
    st.download_button("Export approved drafts CSV", data=drafts[drafts["status"] == "Approved"].to_csv(index=False).encode("utf-8-sig"), file_name="content_drafts_approved.csv", mime="text/csv")
    st.download_button("Export published drafts CSV", data=drafts[drafts["status"] == "Published"].to_csv(index=False).encode("utf-8-sig"), file_name="content_drafts_published.csv", mime="text/csv")

with tabs[13]:
    st.subheader("SEO Programmatic Pages")
    st.caption("Các trang này được tạo local/static. Không auto-post, không tự chạy ads, và sitemap được quét tự động từ site_output.")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Review pages", count_site_pages("*/index.html") - count_site_pages("comparisons/*/index.html") - count_site_pages("blog/*/index.html"))
    c2.metric("Comparison pages", count_site_pages("comparisons/*/index.html"))
    c3.metric("Top list pages", count_site_pages("best-*/index.html"))
    c4.metric("Pricing pages", count_site_pages("*-pricing/index.html"))
    c5.metric("URLs trong sitemap", sitemap_url_count())
    st.markdown("### Regenerate")
    st.code("python main.py\npython scripts/generate_sitemap.py\npython scripts/validate_site.py", language="powershell")
    if st.button("Regenerate programmatic pages"):
        run_pipeline()
        st.success("Đã chạy lại pipeline. Programmatic pages và sitemap đã được cập nhật.")
    st.markdown("### Nhóm page")
    st.write("- Comparison pages: `/comparisons/<tool-a>-vs-<tool-b>/`")
    st.write("- Top list pages: `/best-ai-writing-tools/`, `/best-crm-tools/`, ...")
    st.write("- Pricing/intent pages: `/cursor-pricing/`, `/semrush-pricing/`, ...")

with tabs[14]:
    st.subheader("Affiliate Tracking")
    st.caption("Theo dõi click CTA/outbound tối thiểu. Không lưu IP, email, cookie cá nhân hoặc thông tin định danh.")
    webhook_configured = bool(os.getenv("CLICK_WEBHOOK_URL", "").strip())
    st.markdown("### Production Storage Status")
    s1, s2, s3 = st.columns(3)
    s1.success("Local CSV mode\n\n`data/click_events.csv`")
    s2.info("Netlify logs mode\n\nFunction logs")
    if webhook_configured:
        s3.success("Webhook mode\n\n`CLICK_WEBHOOK_URL` đã set")
    else:
        s3.warning("Webhook mode\n\nChưa set `CLICK_WEBHOOK_URL`")
    if not webhook_configured:
        st.warning("Production tracking hiện vẫn ghi Netlify logs. Nếu chưa set webhook thì dữ liệu production chưa lưu bền vững. Bước A1.3 khuyến nghị nối Google Sheet webhook hoặc Supabase.")
    st.markdown("### Webhook Setup Checklist")
    checklist = pd.DataFrame(
        [
            {
                "Việc cần làm": "Tạo Google Sheet mới và đặt sheet đầu tiên là click_events",
                "Trạng thái": "Bạn tự kiểm tra",
            },
            {
                "Việc cần làm": "Dán code từ scripts/google_sheet_click_webhook.gs vào Apps Script",
                "Trạng thái": "Bạn tự kiểm tra",
            },
            {
                "Việc cần làm": "Deploy Apps Script dạng Web app, Execute as Me, access Anyone",
                "Trạng thái": "Bạn tự kiểm tra",
            },
            {
                "Việc cần làm": "Set CLICK_WEBHOOK_URL trong Netlify Environment variables",
                "Trạng thái": "Đã set" if webhook_configured else "Chưa set",
            },
            {
                "Việc cần làm": "Redeploy site trên Netlify",
                "Trạng thái": "Bạn tự kiểm tra",
            },
            {
                "Việc cần làm": "Test bằng python scripts/test_click_webhook.py",
                "Trạng thái": "Bạn tự kiểm tra",
            },
        ]
    )
    st.dataframe(checklist, use_container_width=True, hide_index=True)
    st.code("python scripts/test_click_webhook.py", language="powershell")
    st.caption("Nếu chưa set CLICK_WEBHOOK_URL trên Netlify thì production click chỉ có trong Netlify Function logs, chưa lưu bền vững vào Google Sheet.")
    with st.expander("Cách tracking hoạt động ở local và production", expanded=False):
        st.write("- Local mode: dashboard đọc `data/click_events.csv`. Khi chạy Netlify Function local, event có thể append vào CSV này.")
        st.write("- Production mode: `/go/<tool>/` POST event tới `/.netlify/functions/track-click`, Netlify Function ghi JSON vào Function logs.")
        st.write("- Webhook mode: nếu Netlify có biến `CLICK_WEBHOOK_URL`, Function sẽ POST event sang webhook để lưu bền vững.")
        st.write("- Nếu Function lỗi hoặc mạng chậm, user vẫn được redirect sang official/affiliate URL, không bị mất luồng click.")
    clicks = load_click_events()
    if clicks.empty:
        st.info("Chưa có click event trong `data/click_events.csv`. Các trang `/go/<tool>/` đã sẵn sàng để redirect và tracking local/import sau này.")
    suspicious_mask = pd.Series(False, index=clicks.index)
    if not clicks.empty and "is_suspicious" in clicks.columns:
        suspicious_mask = clicks["is_suspicious"].astype(str).str.lower().isin(["true", "1", "yes", "y"])
    suspicious_count = int(suspicious_mask.sum()) if not clicks.empty else 0
    valid_count = max(0, len(clicks) - suspicious_count)
    suspicious_rate = (suspicious_count / len(clicks) * 100) if len(clicks) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng click", len(clicks))
    c2.metric("Valid clicks", valid_count)
    c3.metric("Suspicious clicks", suspicious_count)
    c4.metric("Suspicious rate", f"{suspicious_rate:.1f}%")
    c1, c2, c3 = st.columns(3)
    c1.metric("Số tool có click", clicks["tool_slug"].nunique() if not clicks.empty and "tool_slug" in clicks.columns else 0)
    c2.metric("Số page có click", clicks["source_page"].nunique() if not clicks.empty and "source_page" in clicks.columns else 0)
    c3.metric("CTR", "chưa có dữ liệu impression")

    if not clicks.empty:
        st.markdown("### Click theo tool")
        st.dataframe(clicks.groupby(["tool_slug", "tool_name"]).size().reset_index(name="clicks").sort_values("clicks", ascending=False), use_container_width=True)
        st.markdown("### Click theo page")
        st.dataframe(clicks.groupby("source_page").size().reset_index(name="clicks").sort_values("clicks", ascending=False).head(10), use_container_width=True)
        st.markdown("### Click theo CTA")
        st.dataframe(clicks.groupby("cta_label").size().reset_index(name="clicks").sort_values("clicks", ascending=False), use_container_width=True)
        st.markdown("### Top 10 tool")
        st.dataframe(clicks.groupby("tool_name").size().reset_index(name="clicks").sort_values("clicks", ascending=False).head(10), use_container_width=True)
        suspicious_clicks = clicks[suspicious_mask]
        st.markdown("### Click nghi ngờ")
        c1, c2 = st.columns(2)
        with c1:
            st.write("Top suspicious tools")
            if suspicious_clicks.empty:
                st.info("Chưa có click nghi ngờ.")
            else:
                st.dataframe(
                    suspicious_clicks.groupby(["tool_slug", "tool_name"]).size().reset_index(name="suspicious_clicks").sort_values("suspicious_clicks", ascending=False).head(10),
                    use_container_width=True,
                )
        with c2:
            st.write("Top suspicious pages")
            if suspicious_clicks.empty:
                st.info("Chưa có click nghi ngờ.")
            else:
                st.dataframe(
                    suspicious_clicks.groupby("source_page").size().reset_index(name="suspicious_clicks").sort_values("suspicious_clicks", ascending=False).head(10),
                    use_container_width=True,
                )
        st.markdown("### Chi tiết click")
        click_filter = st.radio("Bộ lọc", ["All", "Valid", "Suspicious"], horizontal=True, key="affiliate_tracking_click_filter")
        detail_clicks = clicks
        if click_filter == "Valid":
            detail_clicks = clicks[~suspicious_mask]
        elif click_filter == "Suspicious":
            detail_clicks = suspicious_clicks
        preferred_columns = [
            "timestamp",
            "tool_slug",
            "tool_name",
            "source_page",
            "cta_label",
            "event_type",
            "is_suspicious",
            "suspicious_reason",
            "click_quality_score",
            "session_id",
            "click_id",
            "page_load_seconds",
            "user_agent_hint",
            "target_url",
        ]
        visible_columns = [column for column in preferred_columns if column in detail_clicks.columns]
        st.dataframe(detail_clicks.sort_values("timestamp", ascending=False)[visible_columns], use_container_width=True)
        st.download_button("Export click_events.csv", data=clicks.to_csv(index=False).encode("utf-8-sig"), file_name="click_events.csv", mime="text/csv")

    st.markdown("### Test tracking URL")
    st.code("/go/cursor/?src=/cursor/&cta=official_site&debug=1", language="text")
    st.write("Mở URL có `debug=1` để xem trang redirect mà không tự chuyển đi ngay.")
    st.write("Test spam: mở cùng URL nhiều hơn 3 lần trong 5 phút trên cùng trình duyệt, sau đó import localStorage vào CSV.")
    st.markdown("### Import click events từ trình duyệt")
    st.caption("Trên site static, browser lưu event vào `localStorage.aiip_click_events`. Dán JSON đó vào đây để nhập vào CSV local.")
    imported_json = st.text_area("localStorage.aiip_click_events JSON", height=120, placeholder='[{"tool_slug":"cursor","tool_name":"Cursor","source_page":"/cursor/","cta_label":"official_site"}]')
    if st.button("Import click events vào CSV"):
        try:
            records = json.loads(imported_json or "[]")
            if isinstance(records, dict):
                records = [records]
            imported = 0
            for record in records:
                if isinstance(record, dict):
                    append_click_event({column: str(record.get(column, "")) for column in CLICK_EVENT_COLUMNS})
                    imported += 1
            st.success(f"Đã import {imported} click events vào data/click_events.csv.")
        except Exception as exc:
            st.error(f"Không đọc được JSON: {exc}")

with tabs[15]:
    st.subheader("Social Distribution")
    st.warning("Local-safe mode: no auto-posting before approval. Facebook, LinkedIn and X/Twitter are copy-ready only.")
    accounts = load_social_accounts()
    telegram_cfg = accounts.get("telegram", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Generated posts", len(social_posts))
    c2.metric("Queue items", len(social_queue))
    c3.metric("Scheduled", int((social_queue["status"].astype(str) == "Scheduled").sum()) if not social_queue.empty and "status" in social_queue.columns else 0)
    c4.metric("Published", int((social_queue["status"].astype(str) == "Published").sum()) if not social_queue.empty and "status" in social_queue.columns else 0)

    st.markdown("### Social account config")
    st.write(f"Telegram enabled: {telegram_cfg.get('enabled', False)} | token set: {bool(telegram_cfg.get('bot_token'))} | chat_id set: {bool(telegram_cfg.get('chat_id'))}")
    st.caption("Use `.env` for secrets: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Do not hardcode tokens.")

    approved_articles = review_queue[review_queue["status"].astype(str) == "Published"] if not review_queue.empty else pd.DataFrame()
    st.markdown("### Generate social content from published article")
    if approved_articles.empty:
        st.info("No Published article is available for a social pack yet. Use Content Approval -> Publish to Site first.")
    else:
        article_id = st.selectbox("Approved article", approved_articles["draft_id"].astype(str).tolist(), key="social_article_id")
        article = approved_articles[approved_articles["draft_id"].astype(str) == article_id].iloc[0].to_dict()
        st.write(f"Title: {article.get('title', '')}")
        p1, p2, p3, p4 = st.columns(4)
        platforms = []
        if p1.checkbox("Facebook", value=True, key="social_tab_fb"):
            platforms.append("facebook")
        if p2.checkbox("Telegram", value=True, key="social_tab_tg"):
            platforms.append("telegram")
        if p3.checkbox("LinkedIn", value=True, key="social_tab_li"):
            platforms.append("linkedin")
        if p4.checkbox("Twitter/X", value=True, key="social_tab_tw"):
            platforms.append("twitter")
        if st.button("Generate social variations", key="social_tab_generate"):
            if not str(article.get("target_url", "")).strip():
                st.error("Publish to Site first so social posts use a real URL.")
                st.stop()
            records = generate_social_pack(article, platforms)
            boost_path = save_distribution_boost(str(article.get("slug", article_id)), str(article.get("title", "")), str(article.get("target_url", "")), str(article.get("draft_content", "")))
            st.success(f"Generated {len(records)} social posts. Distribution boost: {boost_path}")
            social_posts = read_social_post_report()

    st.markdown("### Social post report")
    social_posts = read_social_post_report()
    if social_posts.empty:
        st.info("No social posts yet. Generate them from an approved article.")
    else:
        st.dataframe(social_posts, use_container_width=True, hide_index=True)
        tab_selection_version = int(st.session_state.get("social_tab_queue_selection_version", 0))
        tab_options = social_posts["post_id"].astype(str).tolist()
        tab_default = [item for item in st.session_state.get("social_tab_post_ids_value", []) if item in tab_options]
        post_ids = st.multiselect(
            "Bài viết cần xếp hàng chờ",
            tab_options,
            default=tab_default,
            key=f"social_tab_post_ids_{tab_selection_version}",
        )
        st.session_state["social_tab_post_ids_value"] = post_ids
        if st.button("Clear Pending Selection", key="social_tab_clear_pending_selection"):
            st.session_state["social_tab_post_ids_value"] = []
            st.session_state["social_tab_queue_selection_version"] = tab_selection_version + 1
            st.rerun()
        platform_filter = st.multiselect("Platforms", sorted(social_posts["platform"].astype(str).unique().tolist()), default=sorted(social_posts["platform"].astype(str).unique().tolist()), key="social_tab_platforms")
        schedule_time = st.text_input("Schedule start ISO", value="", key="social_tab_schedule")
        random_delay = st.number_input("Random delay minutes", min_value=0, max_value=240, value=15, step=5, key="social_tab_delay")
        if st.button("Approve + add to queue", key="social_tab_enqueue"):
            before = len(load_queue())
            social_queue = enqueue_posts(post_ids, platform_filter, schedule_time, int(random_delay))
            social_queue = save_queue(social_queue)
            write_distribution_summary(social_queue)
            added = max(0, len(social_queue) - before)
            skipped = max(0, len(post_ids) - added)
            st.success(f"Queued {added} posts. Skipped {skipped} duplicates. They will not publish until queue processing is run.")
            st.session_state["social_tab_post_ids_value"] = []
            st.session_state["social_tab_queue_selection_version"] = tab_selection_version + 1
            st.rerun()

    st.markdown("### Publish queue")
    social_queue = load_queue()
    if not social_queue.empty:
        remove_ids = st.multiselect("Remove queued items permanently", social_queue["queue_id"].astype(str).tolist(), key="social_tab_remove_queue_items")
        if st.button("Remove selected queued items", key="social_tab_remove_queue_button"):
            social_queue, removed = remove_queue_items(remove_ids)
            write_distribution_summary(social_queue)
            st.success(f"Removed {removed} queued rows and saved data/social_publish_queue.csv.")
            st.rerun()
    st.dataframe(social_queue, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    if c1.button("Dry-run due queue", key="social_tab_dry_run"):
        result = process_due_queue(dry_run=True)
        write_distribution_summary(load_queue())
        st.info(result)
    if c2.button("Process due queue (Telegram only)", key="social_tab_process"):
        result = process_due_queue(dry_run=False)
        write_distribution_summary(load_queue())
        st.info(result)
    st.markdown("### Manual export")
    if not social_posts.empty:
        st.download_button("Download social_post_report.csv", data=social_posts.to_csv(index=False).encode("utf-8-sig"), file_name="social_post_report.csv", mime="text/csv")
    if not social_queue.empty:
        st.download_button("Download social_publish_queue.csv", data=social_queue.to_csv(index=False).encode("utf-8-sig"), file_name="social_publish_queue.csv", mime="text/csv")

with tabs[16]:
    render_manual_social_distribution_page()


def _render_manual_social_distribution_page_legacy_unused() -> None:
    st.header("Phân phối xã hội")
    st.warning("Local-safe: chỉ tạo nội dung và cập nhật CSV. Không auto-post, không gọi API ngoài, không deploy.")
    calendar = ensure_social_distribution_assets()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng bài seed", len(calendar))
    c2.metric("Chờ duyệt", int((calendar["status"].astype(str) == "Pending Review").sum()) if not calendar.empty else 0)
    c3.metric("Approved", int((calendar["status"].astype(str) == "Approved").sum()) if not calendar.empty else 0)
    c4.metric("Posted", int((calendar["status"].astype(str) == "Posted").sum()) if not calendar.empty else 0)

    if calendar.empty:
        st.info("Chưa có social calendar. Chạy `python main.py` để tạo seed.")
        return

    f1, f2 = st.columns(2)
    platform_options = ["All"] + sorted(calendar["platform"].astype(str).unique().tolist())
    status_options = ["All"] + SOCIAL_REVIEW_STATUSES
    platform_filter = f1.selectbox("Lọc platform", platform_options, key="manual_social_platform")
    status_filter = f2.selectbox("Lọc status", status_options, key="manual_social_status")

    filtered = calendar.copy()
    if platform_filter != "All":
        filtered = filtered[filtered["platform"].astype(str) == platform_filter]
    if status_filter != "All":
        filtered = filtered[filtered["status"].astype(str) == status_filter]

    st.markdown("### Bài chờ duyệt")
    st.dataframe(
        filtered[["id", "platform", "post_title", "target_url", "status", "scheduled_date", "scheduled_time"]],
        use_container_width=True,
        hide_index=True,
    )

    if filtered.empty:
        st.info("Không có bài phù hợp bộ lọc.")
        return

    selected_id = st.selectbox("Chọn bài để preview", filtered["id"].astype(str).tolist(), key="manual_social_selected")
    row = calendar[calendar["id"].astype(str) == selected_id].iloc[0].to_dict()
    st.markdown(f"### Preview: {row.get('post_title', '')}")
    st.caption(f"Platform: {row.get('platform', '')} | Status: {row.get('status', '')} | Schedule: {row.get('scheduled_date', '')} {row.get('scheduled_time', '')}")
    st.text_area("Nội dung copy-ready", value=str(row.get("post_body", "")), height=260, key=f"manual_social_body_{selected_id}")
    st.code(str(row.get("target_url", "")))
    note = st.text_input("Ghi chú khi cập nhật trạng thái", value=str(row.get("notes", "")), key=f"manual_social_note_{selected_id}")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Approved", key=f"manual_social_approve_{selected_id}"):
        update_calendar_status(selected_id, "Approved", note)
        st.success("Đã duyệt và lưu vào data/social_calendar.csv")
        st.rerun()
    if b2.button("Rejected", key=f"manual_social_reject_{selected_id}"):
        update_calendar_status(selected_id, "Rejected", note)
        st.success("Đã từ chối và lưu vào data/social_calendar.csv")
        st.rerun()
    if b3.button("Needs edit", key=f"manual_social_edit_{selected_id}"):
        update_calendar_status(selected_id, "Needs edit", note)
        st.success("Đã đánh dấu cần chỉnh sửa.")
        st.rerun()
    if b4.button("Mark Posted", key=f"manual_social_posted_{selected_id}"):
        update_calendar_status(selected_id, "Posted", note)
        st.success("Đã đánh dấu đã đăng thủ công.")
        st.rerun()

    st.markdown("### Export")
    st.download_button(
        "Download social_calendar.csv",
        data=load_social_calendar().to_csv(index=False).encode("utf-8-sig"),
        file_name="social_calendar.csv",
        mime="text/csv",
    )
    st.caption("Markdown copy files are saved in `draft_output/social_queue/`.")
