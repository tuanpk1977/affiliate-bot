# Affiliate Research Bot

Python bot for collecting affiliate program signals from candidate websites, scoring them, and generating a ranked report.

The business goal is to find affiliate programs strong enough to package as paid information for affiliate marketers. The scoring also includes an `ad_readiness_score` so the best leads can later move into automated ad testing.

## AI Affiliate Intelligence Platform

Phần mới nằm song song với bot cũ và không thay đổi `src/main.py` hoặc flow `runbot.bat` hiện tại.

Mục tiêu của nền tảng mới là biến bot thành:

```text
OpenAffiliate + Automation + AI Decision Engine + ROI Optimizer
```

Nền tảng mới tự tạo:

- Bảng xếp hạng affiliate offers: `data/offer_scores.csv`
- Market intelligence theo niche: `data/market_insights.csv`
- Keyword intelligence: `data/keywords.csv`
- Google Ads CSV để upload thủ công: `data/ads_google.csv`
- Bing/Microsoft Ads CSV để upload thủ công: `data/ads_bing.csv`
- Landing pages có affiliate disclosure: `landing_pages/output/`
- ROI tracker và quyết định pause/watch/optimize/scale: `data/roi_report.csv`
- Report tổng hợp: `data/report_summary.md`

Chạy nền tảng mới:

```powershell
pip install -r requirements.txt
python scripts/generate_tool_screenshots.py
python main.py
python -m streamlit run dashboard/app.py
```

Tạo lại ảnh minh họa/mockup cho các review page bất cứ lúc nào:

```powershell
python scripts/generate_tool_screenshots.py
python main.py
```

Kiểm tra priority pages sau khi upload `site_output/` lên Netlify:

```powershell
python scripts/live_qa_priority_pages.py
```

Script sẽ kiểm tra 5-10 URL live mẫu trên `https://review.mssmileenglish.com/` và xuất kết quả vào:

```text
data/live_priority_page_qa.csv
```

Script sẽ tạo ảnh PNG 1200x720 tại:

```text
assets/screenshots/
```

Khi chạy `python main.py`, các ảnh này được copy sang:

```text
site_output/assets/screenshots/
```

Nếu review page có ảnh đúng slug, ví dụ `assets/screenshots/gamma.png`, trang sẽ hiển thị ảnh thật. Nếu chưa có ảnh, trang giữ placeholder và không lỗi.

Hoặc double-click:

```text
run_platform.bat
```

Sau khi chạy, mở dashboard tại:

```text
http://localhost:8501
```

Dashboard có 8 tab:

- Offer Rankings
- Offer Detail
- Keyword Intelligence
- Ads Generator
- Landing Pages
- Profit Simulator
- ROI Tracker
- Reports

Quan trọng:

- Version này không dùng Google Ads API thật.
- Không tự chạy tiền quảng cáo.
- CSV luôn để upload thủ công và review trước.
- Ads/landing page tránh claim sai sự thật và có affiliate disclosure.
- Nếu compliance là `BLOCKED`, hệ thống không tạo ads cho offer đó.

Muốn thêm offer thật, sửa file:

```text
data/offers.csv
```

Các cột quan trọng:

```csv
offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes
```

Muốn cập nhật số liệu ads thật, sửa/export vào:

```text
data/campaign_results.csv
```

Sau đó chạy lại:

```powershell
python main.py
```

Decision engine dùng rule:

- ROI < -20%: `PAUSE`
- ROI -20% đến 10%: `WATCH`
- ROI 10% đến 30%: `OPTIMIZE`
- ROI > 30%: `SCALE`

## Setup

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `data/input/projects_seed.csv` with candidate projects:

```csv
brand_name,website,category,source,notes
Example SaaS,https://example.com,saas,manual,initial test
```

Telegram delivery is optional. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` only if you want report delivery.

## Run

Double-click:

```text
runbot.bat
```

The batch file will install dependencies if needed, discover affiliate candidates from trusted sources, run the bot, print the decision summary, and open the output folder.

Manual run:

```powershell
python src/main.py
```

Outputs are written to:

- `data/output/projects_raw.csv`
- `data/output/projects_scored.csv`
- `data/output/top_report.txt`
- `data/output/decision_summary.txt`
- `data/output/discovered_projects.csv`
- `data/output/ad_launch_plan.csv`
- `data/output/google_ads_upload_template.csv`
- `data/output/microsoft_ads_upload_template.csv`
- `data/output/ads_manual_steps.txt`
- `data/output/landing_pages_index.csv`
- `data/output/roi_report.csv`
- `data/output/roi_summary.txt`
- `data/output/crypto_listing_watchlist.csv`
- `data/output/crypto_listing_summary.txt`
- `landing_pages/`
- `data/logs/bot.log`

For manual verification, use `data/input/manual_review_template.csv` as the review sheet format.

## Where To See Results

- `data/output/decision_summary.txt`: easiest file to read first. It tells which affiliate projects are worth selling as information and which are worth preparing for ads.
- `data/output/top_report.txt`: detailed ranked list of affiliate leads.
- `data/output/projects_scored.csv`: full spreadsheet with every score, status, checklist, audience, and selling angle.
- `data/output/projects_raw.csv`: raw crawl and parser output.
- `data/output/discovered_projects.csv`: candidates automatically found from trusted discovery sources.
- `data/output/ad_launch_plan.csv`: leads that passed ads precheck and the landing page/ad plan for each lead.
- `data/output/google_ads_upload_template.csv`: starter upload template for Google Ads. Keep campaigns paused until manual review is done.
- `data/output/microsoft_ads_upload_template.csv`: starter upload template for Microsoft/Bing Ads. Keep campaigns paused until manual review is done.
- `data/output/ads_manual_steps.txt`: Vietnamese instructions for what you must do before turning ads on.
- `landing_pages/`: generated static HTML landing pages for ad candidates.
- `data/output/landing_pages_index.csv`: index of generated landing pages.
- `data/input/ad_results.csv`: paste/export Google/Bing Ads performance here.
- `data/output/roi_report.csv`: ROI calculations and pause/keep/scale recommendation.
- `data/output/roi_summary.txt`: Vietnamese ROI summary.
- `data/output/crypto_listing_watchlist.csv`: official-source crypto listing watchlist for research.
- `data/output/crypto_listing_summary.txt`: Vietnamese summary of new/upcoming listing signals.

## Ads Automation Scope

The bot can automatically:

- Find affiliate leads.
- Score and rank leads.
- Detect basic ads policy risks from affiliate terms.
- Block high-risk leads from ad templates.
- Generate landing page requirements.
- Generate Google Ads and Microsoft/Bing Ads upload templates.
- Generate static landing pages.
- Calculate ROI from exported ad results.
- Recommend pause/keep/scale for campaigns.

You still need to manually:

- Own and configure a domain.
- Create the landing page on your domain.
- Add affiliate disclosure, Privacy Policy, Terms, and Contact pages.
- Paste your affiliate link into the landing page CTA.
- Verify PPC/paid search/brand bidding rules in the affiliate terms.
- Complete Google/Microsoft verification or crypto/finance certification when required.
- Upload the template and keep campaigns paused until final review.
- Publish generated landing pages to your domain.
- Export ad performance into `data/input/ad_results.csv` after testing.

## ROI Tracking

After campaigns get traffic, export or enter results into:

```csv
campaign,cost,clicks,conversions,revenue,notes
My Campaign,25,100,2,60,first test
```

Then run:

```powershell
python src/main.py
```

Check:

- `data/output/roi_report.csv`
- `data/output/roi_summary.txt`

## Crypto Listing Watchlist

The bot can monitor official listing announcement pages and create a research watchlist.

Outputs:

- `data/output/crypto_listing_watchlist.csv`
- `data/output/crypto_listing_summary.txt`

Important: this is not a buy/sell recommendation. New listings can pump and dump quickly. Always verify official announcements, tokenomics, vesting, liquidity, market cap, audit, team, and legal risk before buying.

## How Auto Discovery Works

The bot reads `data/input/discovery_sources.csv`, visits those source pages, extracts candidate project links with affiliate/partner/referral signals, removes duplicates, then evaluates each candidate.

Edit `DISCOVERY_LIMIT` in `.env` to control how many candidates it checks per run:

```env
DISCOVERY_LIMIT=25
```

You can add more trusted sources to `data/input/discovery_sources.csv`:

```csv
source_name,source_url,category,trust_level,notes
My Source,https://example.com/affiliate-programs,saas,high,Trusted directory
```

## How To Add Projects

Edit `data/input/projects_seed.csv`:

```csv
brand_name,website,category,source,notes
Tool Name,https://example.com,saas,manual,short note
AI Product,https://example.ai,ai,twitter,found from post
```

Recommended categories:

- `ai`
- `saas`
- `devtools`
- `crypto`
- `finance`
- `marketing`
- `education`
- `ecommerce`

## Scoring Meaning

- `affiliate_quality_score`: how strong and clear the affiliate program looks.
- `data_product_value_score`: how sellable this lead is as paid information.
- `ad_readiness_score`: how ready this project is for future ad testing.
- `total_score`: blended priority score used for ranking.
- `recommended_action`: what to do next before selling or advertising the lead.
- `review_status`: whether the lead is ready for verification, needs manual review, needs more research, or belongs in the watchlist.
- `sale_status`: whether this can be packaged after proof, must be verified before selling, is blocked, or should not be sold yet.
- `ads_status`: whether this can move toward ad testing after terms review.
- `verification_checklist`: the exact items to verify before selling the lead or running ads.

## Manual Verification Workflow

1. Run the bot and open `data/output/projects_scored.csv`.
2. Filter by `sale_status` and `review_status`.
3. Manually open `manual_review_url` or `affiliate_url`.
4. Confirm commission, cookie window, payout, allowed traffic sources, and program activity.
5. Capture proof before selling the information.
6. Only move a lead toward ads when `ads_status` is not `not_ready_for_ads` and traffic restrictions are confirmed.
