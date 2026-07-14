# CLI Reference

## Main menu

`runbot_menu.bat` provides: 1 Week start; 2 Tue-Sun; 3 Custom topic; 4 Dashboard server; 5 Status; 6 Live status; 7 Block reasons; 8 Publish approved with smart validation and Git push; 9 Affiliate partner; A Exit (menu 10); B Strict full-site audit (menu 11); C SEO Engine (menu 12); D Reset stale unpublished (menu 13). Windows `choice` accepts one key, so operator entries 10-13 are shown as A-D.

## Editorial CLI

```text
trend                    discover and score dated topics
daily-followup           preview/create Tue-Sun angles from weekly roots; never discovers topics
morning                  discovery, drafts, and dashboard
draft                    generate drafts for a dated queue
approve / reject         record one human decision
publish                  publish an approved batch path
publish-ready            publish exact normalized Ready candidates
validate-batch           smart selected or strict full-site validation
prepare-article-output   copy one exact Ready article to output paths
publish-dry-run          non-mutating exact publish/stage plan
autofix-batch            apply supported batch validation fixes
request-topic            custom topic/cluster intake
partner-intake           affiliate partner profile and cluster
status                   compact status; --json for full payload
check-live               local/docs/git/live report
diagnose-article         read-only one-article gate diagnostic
diagnose-batch           deterministic candidate diagnostics
build-selected           bounded exact-slug preparation/build
publish-lock-status      inspect publish lock
clear-stale-publish-lock explicitly clear verified stale lock
recover-interrupted-preparation guarded state recovery with --confirm
reset-unpublished        dry-run-first stale archival reset
open                     resolve/open dashboard paths
serve                    local interactive dashboard HTTP server
```

Most dated commands default to today. Use `--date YYYY-MM-DD` for a specific batch. `publish-ready` uses smart validation unless `--validation-mode strict` is explicitly requested. Expected no-ready returns a distinct non-success automation status while menu option 8 handles it and returns safely. Unexpected validation, JSON, Git, push, permission, and other failures remain errors.

## Safe operational examples

```powershell
python editorial_console.py diagnose-batch --date YYYY-MM-DD
python editorial_console.py daily-followup --count 10 --date YYYY-MM-DD --dry-run
python editorial_console.py daily-followup --count 10 --date YYYY-MM-DD --confirm
python scripts/codex_write_daily_articles.py --date latest --count 10 --depth deep
python editorial_console.py publish-dry-run --date YYYY-MM-DD --slug SLUG
python editorial_console.py validate-batch --date YYYY-MM-DD --mode smart
python editorial_console.py serve --date YYYY-MM-DD --open
python editorial_console.py reset-unpublished --dry-run
```

The SEO submenu is documented in `SEO_ENGINE_BOUNDARY.md`. Commands that mutate approval, publish, reset, or lock state should not be used as test fixtures against real queues.
