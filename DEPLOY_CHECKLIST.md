# Deploy Checklist

Use this checklist before uploading the static site to Netlify Drop.

## 1. Build and check locally

Run from the project root:

```powershell
python main.py
python scripts/final_predeploy_check.py
python scripts/validate_navigation_pages.py
python scripts/validate_category_pages.py
python scripts/validate_pricing_pages.py
python scripts/validate_comparison_pages.py
python scripts/validate_review_pages.py
python scripts/validate_content_quality.py
python scripts/validate_site.py
python scripts/validate_go_pages.py
python -m unittest discover -s tests
```

Open these reports:

- `data/final_predeploy_report.csv`
- `data/final_predeploy_summary.txt`

Deploy only if the final predeploy check says `PASS`.

## 2. Upload the correct folder

Upload only:

```text
site_output/
```

Do not upload the whole project folder when using Netlify Drop.

## 3. Test 5 live URLs after deploy

After Netlify finishes the upload, test:

- `https://smileaireviewhub.com/`
- `https://smileaireviewhub.com/reviews/`
- `https://smileaireviewhub.com/comparisons/`
- `https://smileaireviewhub.com/pricing/`
- `https://smileaireviewhub.com/categories/`

Each page should load with no 404.

## 4. Test one tracking link

Open:

```text
https://smileaireviewhub.com/go/cursor/?src=/cursor/&cta=official_site&debug=1
```

Confirm the debug page shows:

- `tool_slug`
- `target_url`
- webhook/function status
- payload

Then test without `debug=1` and confirm it redirects normally.

## 5. Check Google Sheet click tracking

If `CLICK_WEBHOOK_URL` is set and embedded during build, test one `/go/` click and confirm the Google Sheet receives a new row.

If the Sheet does not update:

- Recheck the Apps Script deployment is a Web App.
- Confirm access is set to `Anyone`.
- Confirm `.env` contains the correct `CLICK_WEBHOOK_URL`.
- Run `python main.py` again after changing `.env`.
- Upload `site_output/` again.

## 6. Do not use Netlify AI Agent

Do not use Netlify AI Agent for this project unless explicitly needed. It is not required for this static deploy and can consume credits.
