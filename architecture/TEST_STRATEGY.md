# Test Strategy

The repository uses `pytest` across domain units, workflow integration, generated-page invariants, and operational safety.

## Test layers

- Unit tests cover scoring, research, source, review, gate normalization, sitemap/indexing, and builders.
- Workflow tests cover approval, dashboard actions, state consistency, dry-run, targeted build, reset, and status reporting.
- Safety regressions prove published articles are rejected by dry-run, unrelated staging paths are excluded, lock/recovery guards hold, and non-strict indexing cannot fail a successful deploy.
- Generated-page tests cover canonical, breadcrumbs, FAQ/Article/author schema, language integrity, and page families.
- Post-deploy indexing tests distinguish targeted publish preflight from strict full-site audit and verify explicit missing-credential results.

## Commands

```powershell
python -m pytest
python -m pytest tests/test_publish_workflow_safety.py
python -m pytest tests/test_editorial_console.py tests/test_daily_editorial_workflow.py
python -m pytest tests/test_post_deploy_indexing.py
```

For code changes, run the narrow affected tests first and then the full suite. Documentation-only changes require diff/scope validation but do not require regenerating outputs or running tests.

## Non-destructive test rules

- Use temporary directories/fixtures for queue and output mutation.
- Use `publish-dry-run` for real-batch operational checks.
- Mock Git add/commit/push, network, Cloudflare, and search submissions in tests.
- Never approve, reject, publish, reset, or autofix a real article as test setup.
- Assert exact selected slugs and `would_stage` paths.
- Keep strict full-site failures distinct from targeted publish acceptance.

Known technical debt includes tests that inspect large checked-in generated trees, sensitivity to stale generated artifacts, and the cost/noise of full-site schema/link checks. New tests should prefer deterministic fixtures while retaining a small number of production-tree acceptance checks.
