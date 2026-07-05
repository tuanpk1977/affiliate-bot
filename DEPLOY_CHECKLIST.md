# Deploy Checklist

Use this checklist before deploying `site_output/` to Cloudflare Pages.

## 1. Build and validate locally

From the project root:

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

Open these reports if available:

- `data/final_predeploy_report.csv`
- `data/final_predeploy_summary.txt`

Deploy only if the final predeploy check says `PASS`.

## 2. Ensure output folder is correct

Deploy only the generated static site:

```text
site_output/
```

Do not deploy the full repository directory.

## 3. Verify deployment prerequisites

- `site_output/sitemap.xml` exists.
- `site_output/robots.txt` exists.
- `site_output/indexnow-key.txt` exists if IndexNow is required.
- `BASE_SITE_URL` is set in `.env`.
- `CLOUDFLARE_PAGES_PROJECT` or `CLOUDFLARE_DEPLOY_COMMAND` is configured.

## 4. Deploy to Cloudflare Pages

```powershell
python scripts/deploy_cloudflare.py --project-name YOUR_CLOUDFLARE_PAGES_PROJECT
```

Or run the helper batch file:

```text
run_cloudflare_publish.bat
```

If using `--dry-run`, the deploy command is printed but not executed.

## 5. Validate IndexNow support

After a successful deploy, confirm:

- `https://<site>/indexnow-key.txt` returns the live key.
- `https://<site>/sitemap.xml` is available.
- `https://<site>/robots.txt` is available.

Run:

```powershell
python scripts/check_indexnow_status.py
```

If the check returns failures, fix the site output or key deployment before retrying.

## 6. Smoke test live pages

Visit a sample of live pages:

- `https://<site>/`
- `https://<site>/reviews/`
- `https://<site>/comparisons/`
- `https://<site>/pricing/`
- `https://<site>/categories/`

Also test one tracking page with debug enabled:

```text
https://<site>/go/cursor/?src=/cursor/&cta=official_site&debug=1
```

Confirm the debug page renders and that the same URL without `debug=1` redirects normally.

## 7. Notes

- Cloudflare deploy success is separate from IndexNow success.
- If IndexNow fails, the deploy may still be valid; fix IndexNow configuration afterward.
- Do not commit `.env` or secrets.
- `netlify.toml` is kept for compatibility only. Primary production deployment is Cloudflare Pages.
