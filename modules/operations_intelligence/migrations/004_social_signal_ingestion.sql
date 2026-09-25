PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS social_signal_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_signal_imports (
    import_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_format TEXT NOT NULL,
    checksum TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_signals (
    signal_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    import_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    signal_url TEXT NOT NULL,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    author_account TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    detected_at TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT '',
    engagement_json TEXT NOT NULL DEFAULT '{}',
    official_source_url TEXT NOT NULL DEFAULT '',
    verification_status TEXT NOT NULL,
    duplicate_status TEXT NOT NULL,
    novelty_score REAL NOT NULL,
    relevance_score REAL NOT NULL,
    risk_flags_json TEXT NOT NULL DEFAULT '[]',
    human_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    data_quality_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(import_id) REFERENCES social_signal_imports(import_id)
);

CREATE TABLE IF NOT EXISTS social_signal_provenance (
    provenance_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    import_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    FOREIGN KEY(signal_id) REFERENCES social_signals(signal_id),
    FOREIGN KEY(import_id) REFERENCES social_signal_imports(import_id)
);

CREATE TABLE IF NOT EXISTS social_signal_clusters (
    cluster_id TEXT PRIMARY KEY,
    announcement_key TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_signal_cluster_members (
    cluster_id TEXT NOT NULL,
    signal_id TEXT NOT NULL UNIQUE,
    PRIMARY KEY(cluster_id, signal_id),
    FOREIGN KEY(cluster_id) REFERENCES social_signal_clusters(cluster_id),
    FOREIGN KEY(signal_id) REFERENCES social_signals(signal_id)
);

CREATE TABLE IF NOT EXISTS social_signal_candidates (
    candidate_id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    official_source_url TEXT NOT NULL DEFAULT '',
    verification_status TEXT NOT NULL,
    score REAL NOT NULL,
    priority TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    integration_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    human_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(cluster_id) REFERENCES social_signal_clusters(cluster_id)
);

CREATE TABLE IF NOT EXISTS social_signal_review_events (
    event_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES social_signal_candidates(candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_social_signals_platform ON social_signals(platform);
CREATE INDEX IF NOT EXISTS idx_social_signals_verification ON social_signals(verification_status);
CREATE INDEX IF NOT EXISTS idx_social_candidates_status ON social_signal_candidates(status);
