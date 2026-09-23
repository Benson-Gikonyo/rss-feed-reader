CREATE TABLE feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL UNIQUE CHECK(length(trim(source_url)) > 0),
    site_url TEXT,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    subtitle TEXT NOT NULL DEFAULT '',
    generator TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_fetched_at TEXT,
    etag TEXT,
    last_modified TEXT,
    fetch_url TEXT
);
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    guid TEXT NOT NULL CHECK(length(trim(guid)) > 0),
    url TEXT,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    published_at TEXT,
    author TEXT,
    summary TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    UNIQUE(feed_id, guid)
);
CREATE INDEX idx_articles_feed_published ON articles(feed_id, published_at DESC, id DESC);
