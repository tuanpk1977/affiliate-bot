PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS editorial_memory_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_memory_articles (
    article_id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_memory_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES editorial_memory_articles(article_id),
    fingerprint TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    root_topic TEXT NOT NULL DEFAULT '',
    angle TEXT NOT NULL DEFAULT '',
    keyword TEXT NOT NULL DEFAULT '',
    entities_json TEXT NOT NULL DEFAULT '[]',
    claims_json TEXT NOT NULL DEFAULT '[]',
    cited_sources_json TEXT NOT NULL DEFAULT '[]',
    approval_status TEXT NOT NULL DEFAULT '',
    revision_reasons_json TEXT NOT NULL DEFAULT '[]',
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    written_date TEXT NOT NULL DEFAULT '',
    published_date TEXT NOT NULL DEFAULT '',
    related_articles_json TEXT NOT NULL DEFAULT '[]',
    social_derivatives_json TEXT NOT NULL DEFAULT '[]',
    source_path TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL,
    is_published INTEGER NOT NULL DEFAULT 0 CHECK(is_published IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_memory_snapshots_article ON editorial_memory_snapshots(article_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_memory_snapshots_root_angle ON editorial_memory_snapshots(root_topic, angle);

CREATE TABLE IF NOT EXISTS editorial_memory_events (
    event_id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES editorial_memory_articles(article_id),
    event_fingerprint TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    occurred_at TEXT NOT NULL,
    source_path TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS editorial_memory_claim_reviews (
    review_id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES editorial_memory_snapshots(snapshot_id),
    claim_fingerprint TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'general',
    source_url TEXT NOT NULL DEFAULT '',
    last_verified_at TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('needs_review','reviewed')),
    detected_at TEXT NOT NULL,
    UNIQUE(snapshot_id, claim_fingerprint, reason)
);

CREATE TABLE IF NOT EXISTS editorial_memory_duplicate_reports (
    report_id INTEGER PRIMARY KEY,
    candidate_fingerprint TEXT NOT NULL,
    matched_snapshot_id INTEGER NOT NULL REFERENCES editorial_memory_snapshots(snapshot_id),
    scores_json TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_fingerprint, matched_snapshot_id)
);
