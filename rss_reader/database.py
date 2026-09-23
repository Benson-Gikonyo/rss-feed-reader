"""Application-scoped SQLite connections and transactional persistence."""
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext

from .url_safety import normalize_url

SCHEMA_VERSION = 2


def get_db():
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        g.db = connection
    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def _create_schema(db):
    # executescript commits a pending transaction; execute each DDL statement instead.
    for statement in Path(__file__).with_name("schema.sql").read_text().split(";"):
        if statement.strip():
            db.execute(statement)


def setup_database():
    """Create a fresh schema or leave an initialized database untouched."""
    db = get_db()
    if db.in_transaction:
        raise RuntimeError("Initialize outside an active transaction.")
    with db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        has_tables = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone()
        if version != 0 or has_tables:
            raise RuntimeError(
                "The existing database is not compatible. Configure an empty database; "
                "init-db does not replace existing tables or data."
            )
        _create_schema(db)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create the configured database without replacing existing data."""
    try:
        setup_database()
    except RuntimeError as error:
        raise click.ClickException(str(error)) from None
    except sqlite3.Error:
        raise click.ClickException(
            "Unable to initialize the database. Check its path and permissions. "
            "Existing data was not replaced."
        ) from None
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def get_feed_id(source_url):
    row = get_db().execute("SELECT id FROM feeds WHERE source_url = ?", (normalize_url(source_url),)).fetchone()
    return row["id"] if row else None


def _upsert_articles(db, feed_id, articles):
    for article in articles:
        db.execute("""INSERT INTO articles(feed_id, guid, url, title, published_at, author, summary)
            VALUES (:feed_id, :guid, :url, :title, :published_at, :author, :summary)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                url=excluded.url, title=excluded.title, published_at=excluded.published_at,
                author=excluded.author, summary=excluded.summary""",
                   {"feed_id": feed_id, **asdict(article)})


def save_feed(result, *, feed_id=None):
    """Add or refresh atomically; return (ID, newly_created)."""
    source_url = normalize_url(result.source_url)
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        created = feed_id is None
        if created:
            existing = get_feed_id(source_url)
            if existing is not None:
                return existing, False
            if result.not_modified or result.feed is None:
                raise ValueError("A new feed requires parsed data.")
            feed_id = db.execute(
                "INSERT INTO feeds(source_url, title) VALUES (?, ?)",
                (source_url, result.feed.title),
            ).lastrowid
        else:
            existing = get_feed_by_id(feed_id)
            if existing is None or existing["source_url"] != source_url:
                raise ValueError("Refresh target no longer exists or does not match.")
        if result.not_modified:
            db.execute("""UPDATE feeds SET last_fetched_at=CURRENT_TIMESTAMP,
                etag=COALESCE(?, etag), last_modified=COALESCE(?, last_modified)
                WHERE id=?""", (result.etag, result.last_modified, feed_id))
        else:
            if result.feed is None:
                raise ValueError("Refresh requires parsed data.")
            feed = result.feed
            db.execute("""UPDATE feeds SET site_url=?, title=?, subtitle=?, generator=?,
                updated_at=CURRENT_TIMESTAMP, last_fetched_at=CURRENT_TIMESTAMP,
                etag=?, last_modified=?, fetch_url=? WHERE id=?""", (
                    feed.site_url, feed.title, feed.subtitle, feed.generator,
                    result.etag, result.last_modified, result.fetch_url, feed_id,
                ))
            _upsert_articles(db, feed_id, feed.articles)
        return feed_id, created


def get_articles(feed_id):
    return [dict(row) for row in get_db().execute("""SELECT * FROM articles
        WHERE feed_id=? ORDER BY published_at DESC, id DESC""", (feed_id,))]


def list_feeds():
    return [dict(row) for row in get_db().execute("SELECT * FROM feeds ORDER BY id")]


def get_feed_by_id(feed_id):
    row = get_db().execute("SELECT * FROM feeds WHERE id=?", (feed_id,)).fetchone()
    return dict(row) if row else None


def delete_feed(feed_id):
    db = get_db()
    with db:
        return db.execute("DELETE FROM feeds WHERE id=?", (feed_id,)).rowcount > 0


def update_metadata(feed_id, title, subtitle, generator):
    db = get_db()
    with db:
        db.execute("""UPDATE feeds SET title=?, subtitle=?, generator=?,
            updated_at=CURRENT_TIMESTAMP WHERE id=?""", (title, subtitle, generator, feed_id))
