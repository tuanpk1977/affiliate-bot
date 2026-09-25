CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    identity_key TEXT NOT NULL DEFAULT '',
    verification_status TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),
    human_verified INTEGER NOT NULL DEFAULT 0 CHECK(human_verified IN (0, 1)),
    attributes_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_type, normalized_name, identity_key)
);
CREATE TABLE IF NOT EXISTS aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(entity_id, normalized_alias)
);
CREATE INDEX IF NOT EXISTS idx_alias_normalized ON aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK(status IN ('candidate', 'needs_review', 'verified')),
    confidence REAL NOT NULL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),
    human_verified INTEGER NOT NULL DEFAULT 0 CHECK(human_verified IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_entity_id, relation_type, target_entity_id),
    CHECK(source_entity_id <> target_entity_id)
);
CREATE INDEX IF NOT EXISTS idx_relationship_source ON relationships(source_entity_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relationship_target ON relationships(target_entity_id, relation_type);
CREATE TABLE IF NOT EXISTS provenance (
    provenance_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('entity', 'relationship')),
    subject_id TEXT NOT NULL,
    source_file TEXT NOT NULL DEFAULT '',
    batch_date TEXT NOT NULL DEFAULT '',
    article_slug TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),
    human_verified INTEGER NOT NULL DEFAULT 0 CHECK(human_verified IN (0, 1)),
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(subject_type, subject_id, source_file, batch_date, article_slug, source_url)
);
CREATE INDEX IF NOT EXISTS idx_provenance_subject ON provenance(subject_type, subject_id);
