# Smile AI Review Hub

Smile AI Review Hub combines an older affiliate-program research bot with the current Python editorial automation and static-site publishing system for `https://smileaireviewhub.com/`.

The current production path is:

```text
topic discovery -> research/source checks -> draft -> AI review -> human approval
-> publish gate -> targeted build -> smart validation -> scoped Git push
-> Cloudflare Pages (docs/) -> targeted post-deploy indexing
```

Start the Windows operator menu with:

```powershell
runbot_menu.bat
```

Useful read-only commands:

```powershell
python editorial_console.py status --json
python editorial_console.py diagnose-batch --date YYYY-MM-DD
python editorial_console.py diagnose-article --date YYYY-MM-DD --slug SLUG
python editorial_console.py publish-dry-run --date YYYY-MM-DD --slug SLUG
python editorial_console.py check-live --all --open
```

Run tests with:

```powershell
python -m pytest
```

## Documentation

- `PROJECT_GUIDE.md`: complete operator/developer guide and current project structure.
- `architecture/FIVE_MODULE_BOUNDARIES.md`: ownership and dependency boundaries.
- `architecture/SEO_ENGINE_BOUNDARY.md`: offline SEO scope and prohibited writes.
- `architecture/PUBLISH_WORKFLOW.md`: approval through deployment/indexing.
- `architecture/QUEUE_ARCHITECTURE.md`: queue ownership and lifecycle.
- `architecture/DASHBOARD_ARCHITECTURE.md`: dashboard generation and action flow.
- `architecture/STATE_MACHINE.md`: normalized editorial/publish/deployment states.
- `architecture/CLI_REFERENCE.md`: menu and CLI reference.
- `architecture/DEPLOYMENT.md`: targeted build, Cloudflare, and indexing.
- `architecture/TEST_STRATEGY.md`: test layers and non-destructive safety rules.

## Important boundaries

- `Human Approved` does not mean `Ready for Publish`; all hard gates must pass.
- Dry-run does not build, mutate state, stage, commit, push, deploy, or submit indexing.
- A normal one-article publish uses explicit selected-slug paths; it never stages an entire `upload/<date>` directory.
- `docs/`, `site_output/`, dashboards, reports, and queue files are generated/managed artifacts. Change their owning source or command instead of editing state/output manually.
- Cloudflare Pages deploys `docs/`. `netlify.toml` is retained for compatibility and is not the active production deployment path.
- SEO Engine queue actions are dry-run previews and do not approve or publish content.

The earlier affiliate research bot remains available through `main.py`, `src/`, and `runbot.bat`. The editorial platform is operated through `editorial_console.py`, `runbot_menu.bat`, `modules/`, and `scripts/`.
