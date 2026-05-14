# Social Distribution Workflow

This project keeps social distribution local-safe by default.

## Flow

1. Create or import an article draft.
2. Review it in the Streamlit dashboard.
3. Approve the article.
4. Open the `Social Distribution` tab.
5. Generate platform-specific social posts.
6. Review the generated posts.
7. Add selected posts to `data/social_publish_queue.csv`.
8. Run the queue processor manually when ready.

## Safety Rules

- No social post is published before approval.
- Facebook, LinkedIn, and X/Twitter are copy-ready only.
- Telegram can be sent through Bot API only when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.
- Secrets must be stored in `.env`, not in source code.

## Files

- `config/social_accounts.json`: social account configuration without secrets.
- `draft_output/social_posts/`: generated platform drafts.
- `data/social_post_report.csv`: generated post inventory.
- `data/social_publish_queue.csv`: approved/scheduled queue.
- `data/distribution_summary.txt`: status summary.

## Manual Commands

```powershell
python main.py
python -m streamlit run dashboard/app.py
```

The queue processor is available from the dashboard. Use dry-run first.
