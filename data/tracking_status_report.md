# Tracking Status Report

## Current status

- Static `/go/` redirect pages: enabled.
- Local CSV click event format: `data/click_events.csv`.
- GSC performance import: manual CSV only.
- GA4: optional, controlled by `config/tracking.json`.
- Webhook persistence: configured.

## What works locally/static

- Pages can route outbound CTAs through `/go/<slug>/`.
- UTM tracking URLs can be generated and reported locally.
- Manual GSC exports can be imported from `data/gsc_performance_import.csv`.
- Reports are generated into `data/gsc_page_performance_report.csv`, `data/gsc_query_performance_report.csv`, `data/go_click_performance_report.csv`, and `data/traffic_performance_report.csv`.

## What production persistence needs

GitHub Pages is static and cannot write click events directly to `data/click_events.csv`.
For persistent production click storage, configure a webhook or serverless receiver and keep redirects working even if collection fails.

## Safety rules

- Do not store IP, email, cookies, or personal identifiers in click logs.
- Do not invent traffic, clicks, conversions, or affiliate links.
- Leave webhook and GA4 IDs empty until real accounts are configured.
