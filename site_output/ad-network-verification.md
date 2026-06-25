# Ad Network Verification

This project is a Python static site generator for Smile AI Review Hub.

## Current static publishing structure

- Root project folder: `D:\AFFILATE BOT`
- Generated output folder: `site_output/`
- Cloudflare Pages publish folder: `docs/`
- Root-level public files must exist in the deployed website root, for example:
  - `docs/example-verification.txt`
  - `docs/sw.js`

The active production workflow in this repository is Cloudflare Pages from the
`docs/` folder. There is no Railway deployment configuration in the current
project.

## Recommended workflow for ad network verification files

1. Download the verification file from the ad network.
2. Put the file in the project root:
   - `D:\AFFILATE BOT\<verification-file>`
3. Run the website build/sync workflow:
   - `python build_site.py`
   - `python scripts/sync_site_output_to_docs.py`
4. Confirm the file exists in:
   - `site_output/<verification-file>`
   - `docs/<verification-file>`
5. Commit and push the file plus any build output.
6. Wait for Cloudflare Pages to deploy from GitHub.
7. Verify the live URL:
   - `https://smileaireviewhub.com/<verification-file>`

## HilltopAds

Place the HilltopAds file in the project root, then build and sync so it appears
in `docs/`.

Example live URL:

`https://smileaireviewhub.com/abbb9a24b53b500d9fa5.txt`

## Monetag

Monetag may provide a root `sw.js` verification/service-worker file. Place it in
the project root, then build and sync so it appears in `docs/`.

Example live URL:

`https://smileaireviewhub.com/sw.js`

## Troubleshooting

- If the live URL returns 404, confirm the file exists in `docs/` and the latest
  commit has deployed.
- If a build removes the file from `site_output/`, confirm `build_site.py`
  includes root verification file syncing.
- If the ad network says the file content is wrong, compare the live response
  with the file downloaded from the network.
- Do not add verification files to the sitemap.
- Do not wrap verification files in the site layout.
- Do not rename the verification file.
