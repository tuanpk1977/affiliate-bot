# Social Distribution Workflow

This project uses a local-safe semi-automatic social workflow:

1. Generate seed posts into `data/social_calendar.csv`.
2. Review posts in the dashboard tab `Phân phối xã hội`.
3. Mark each post as `Approved`, `Rejected`, or `Needs edit`.
4. Copy approved posts manually to Facebook, LinkedIn, Telegram, or X/Twitter.
5. Mark the post as `Posted` after publishing manually.

No social API is called by this workflow. No post is published automatically.

## Recommended Manual Posting Flow

- Open `streamlit run dashboard/app.py`.
- Go to `Phân phối xã hội`.
- Filter by `Pending Review`.
- Preview the post body and target URL.
- Approve only posts that match your current publishing plan.
- Copy the post text and publish manually on the selected platform.

## Safe Posting Tips

- Post about 2 items per day across all platforms when starting.
- Do not post the same text to every platform.
- Wait at least a few hours between posts.
- Keep the link pointing to internal review, comparison, or guide pages.
- Do not use direct affiliate links in social posts.
- Do not overuse hashtags.

## Platform Notes

### Facebook
- Use a conversational tone.
- Add one short personal note before the copied text if possible.
- Avoid posting too many links in a short period.

### LinkedIn
- Use practical builder or founder notes.
- Keep claims grounded and avoid hype.
- Good cadence: one thoughtful post per weekday.

### Telegram
- Keep it direct and short.
- Use the link as the main action.
- Good cadence: one morning post and one evening post.

### X/Twitter
- Short hooks work better.
- Threads should be concise.
- Do not repeat the same link too many times in one day.

## Future API Architecture

Placeholder modules live in `modules/social_publishers/`:

- `facebook_publisher.py`
- `linkedin_publisher.py`
- `telegram_publisher.py`
- `twitter_publisher.py`

They are intentionally disabled. Implement API publishing only after the manual approval workflow is stable.
