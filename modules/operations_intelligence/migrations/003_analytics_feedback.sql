PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analytics_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_imports (
    import_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    date_start TEXT NOT NULL DEFAULT '',
    date_end TEXT NOT NULL DEFAULT '',
    row_count INTEGER NOT NULL,
    accepted_row_count INTEGER NOT NULL,
    rejected_row_count INTEGER NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    schema_version TEXT NOT NULL,
    checksum TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS metric_windows (
    window_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES analytics_imports(import_id),
    date_start TEXT NOT NULL,
    date_end TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    comparable INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_metrics (
    metric_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES analytics_imports(import_id),
    article_slug TEXT NOT NULL DEFAULT '', canonical_url TEXT NOT NULL DEFAULT '',
    metric_type TEXT NOT NULL, date_start TEXT NOT NULL, date_end TEXT NOT NULL,
    value REAL NOT NULL, sample_size INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL, confidence REAL NOT NULL,
    data_quality_status TEXT NOT NULL, extras_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_query_metrics (
    metric_id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES analytics_imports(import_id),
    article_slug TEXT NOT NULL DEFAULT '', canonical_url TEXT NOT NULL DEFAULT '', query TEXT NOT NULL,
    date_start TEXT NOT NULL, date_end TEXT NOT NULL, clicks REAL NOT NULL, impressions REAL NOT NULL,
    ctr REAL NOT NULL, average_position REAL NOT NULL, country TEXT NOT NULL DEFAULT '', device TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL, data_quality_status TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS affiliate_metrics (
    metric_id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES analytics_imports(import_id),
    article_slug TEXT NOT NULL DEFAULT '', canonical_url TEXT NOT NULL DEFAULT '', offer_id TEXT NOT NULL DEFAULT '',
    date_start TEXT NOT NULL, date_end TEXT NOT NULL, clicks REAL NOT NULL, conversions REAL NOT NULL,
    revenue REAL, commission REAL, cost REAL, currency TEXT NOT NULL DEFAULT '', roi REAL,
    confidence REAL NOT NULL, data_quality_status TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_metrics (
    metric_id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES analytics_imports(import_id),
    article_slug TEXT NOT NULL DEFAULT '', canonical_url TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL,
    post_id TEXT NOT NULL DEFAULT '', post_url TEXT NOT NULL DEFAULT '', publication_date TEXT NOT NULL DEFAULT '',
    date_start TEXT NOT NULL, date_end TEXT NOT NULL, impressions REAL NOT NULL, views REAL NOT NULL,
    reactions REAL NOT NULL, comments REAL NOT NULL, shares REAL NOT NULL, clicks REAL NOT NULL,
    confidence REAL NOT NULL, data_quality_status TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_candidates (
    candidate_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
    article_slug TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT '', root_topic TEXT NOT NULL DEFAULT '',
    recommendation_type TEXT NOT NULL, recommendation TEXT NOT NULL, reason TEXT NOT NULL,
    metrics_json TEXT NOT NULL, comparison_window TEXT NOT NULL DEFAULT '', confidence REAL NOT NULL,
    priority TEXT NOT NULL, risk_flags_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL,
    human_status TEXT NOT NULL DEFAULT 'pending', interpretation_type TEXT NOT NULL,
    causality_warning TEXT NOT NULL, limitations_json TEXT NOT NULL DEFAULT '[]',
    missing_data_json TEXT NOT NULL DEFAULT '[]', source_import_ids_json TEXT NOT NULL DEFAULT '[]',
    memory_references_json TEXT NOT NULL DEFAULT '[]', graph_references_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL, review_by TEXT NOT NULL DEFAULT '', expires_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS feedback_evidence (
    evidence_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES feedback_candidates(candidate_id),
    import_id TEXT NOT NULL REFERENCES analytics_imports(import_id), evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(candidate_id, import_id, evidence_json)
);

CREATE TABLE IF NOT EXISTS feedback_review_events (
    event_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES feedback_candidates(candidate_id),
    from_status TEXT NOT NULL, to_status TEXT NOT NULL, action TEXT NOT NULL,
    actor TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_backlog_links (
    link_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES feedback_candidates(candidate_id),
    plan_id TEXT NOT NULL DEFAULT '', source_week TEXT NOT NULL DEFAULT '', target_week TEXT NOT NULL DEFAULT '',
    used_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    UNIQUE(candidate_id, plan_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_candidates(status, human_status);
CREATE INDEX IF NOT EXISTS idx_feedback_slug ON feedback_candidates(article_slug);
CREATE INDEX IF NOT EXISTS idx_search_slug ON search_query_metrics(article_slug);
