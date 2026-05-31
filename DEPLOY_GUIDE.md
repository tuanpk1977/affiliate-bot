# GitHub + Netlify Auto Deploy Guide

This project should deploy as a static site from `site_output/`.

The low-credit workflow is:

1. Approve article in the local dashboard.
2. Click `Publish to Site`.
3. Run an incremental local build.
4. Commit changed files.
5. Push to GitHub.
6. Netlify auto deploys from GitHub.

No Netlify Drop is needed.

## 1. Local Build Workflow

Publish one approved draft from the command line:

```powershell
python build_site.py --publish-draft OS-00002 --overwrite
```

Or sync already published articles and refresh sitemap:

```powershell
python build_site.py
```

Full rebuild is still available, but should be used only when needed:

```powershell
python build_site.py --full
```

The incremental build only copies changed files from:

```text
data/published_static_pages/
```

into:

```text
site_output/
```

Then it regenerates:

```text
site_output/sitemap.xml
```

## 2. GitHub Setup

Create a new GitHub repository, then run:

```powershell
git init
git add .
git commit -m "Initial static affiliate site"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Do not commit `.env`.

`site_output/` should be committed because Netlify will publish it directly.

## 3. Netlify Setup

1. Open Netlify.
2. Add new site.
3. Import from GitHub.
4. Choose this repository.
5. Build settings:

```text
Build command: leave empty
Publish directory: site_output
```

The repository already includes `netlify.toml`:

```toml
[build]
  publish = "site_output"
  functions = "netlify/functions"
```

Leaving the build command empty keeps deploys lightweight. Netlify only serves the committed static output.

## 4. Everyday Publishing Flow

After a new article is approved:

```powershell
python build_site.py --publish-draft DRAFT_ID --overwrite
python scripts/validate_site.py
python scripts/final_predeploy_check.py
git add data/content_drafts.csv data/published_static_pages site_output
git commit -m "Publish approved article"
git push
```

Netlify will deploy automatically from GitHub.

## 5. Test After Netlify Deploy

Check:

- `https://smileaireviewhub.com/`
- `https://smileaireviewhub.com/sitemap.xml`
- The new article URL, for example:
  `https://smileaireviewhub.com/cursor-ai-review-a-practical-guide-for-developers-and-ai-coders/`
- One tracking link:
  `https://smileaireviewhub.com/go/cursor/?src=/cursor/&cta=official_site&debug=1`

## 6. What Not To Do

- Do not use Netlify Drop for normal publishing.
- Do not use Netlify AI Agent.
- Do not run a heavy build on Netlify unless needed.
- Do not commit `.env` or secrets.
