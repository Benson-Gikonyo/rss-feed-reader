"""SQLite persistence shared by the web and terminal interfaces."""
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    """Reuse one connection per application context."""
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def setup_database():
    """Create tables without deleting existing data; repair the legacy FK."""
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, link TEXT, subtitle TEXT, generator TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER,
            title TEXT, link TEXT, published TEXT, author TEXT, summary TEXT,
            FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE
        )""")
        foreign_keys = db.execute("PRAGMA foreign_key_list(articles)").fetchall()
        if not any(row[2] == "feeds" and row[6] == "CASCADE" for row in foreign_keys):
            # Copy first: invalid legacy references fail and roll back the repair.
            db.execute("""CREATE TABLE articles_repaired (
                id INTEGER PRIMARY KEY AUTOINCREMENT, feed_id INTEGER,
                title TEXT, link TEXT, published TEXT, author TEXT, summary TEXT,
                FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE
            )""")
            db.execute("""INSERT INTO articles_repaired
                SELECT id, feed_id, title, link, published, author, summary
                FROM articles""")
            db.execute("DROP TABLE articles")
            db.execute("ALTER TABLE articles_repaired RENAME TO articles")
        db.execute("CREATE INDEX IF NOT EXISTS articles_feed_id ON articles(feed_id)")


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Initialize the configured database, preserving existing records."""
    setup_database()
    click.echo("Database initialized.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def get_feed_id(link):
    row = get_db().execute("SELECT id FROM feeds WHERE link = ? ORDER BY id LIMIT 1", (link,)).fetchone()
    return row["id"] if row else None


def _insert_feed(db, title, link, subtitle, generator):
    # Serialize lookup and insertion so concurrent writers cannot add duplicates.
    row = db.execute("SELECT id FROM feeds WHERE link = ? ORDER BY id LIMIT 1", (link,)).fetchone()
    if row:
        return row["id"]
    return db.execute(
        "INSERT INTO feeds(title, link, subtitle, generator) VALUES (?, ?, ?, ?)",
        (title, link, subtitle, generator),
    ).lastrowid


def insert_feed(title, link, subtitle, generator):
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        return _insert_feed(db, title, link, subtitle, generator)


def _insert_article(db, feed_id, title, link, published, author, summary):
    db.execute("""INSERT INTO articles(feed_id, title, link, published, author, summary)
        VALUES (?, ?, ?, ?, ?, ?)""", (feed_id, title, link, published, author, summary))


def insert_article(feed_id, title, link, published, author, summary):
    db = get_db()
    with db:
        _insert_article(db, feed_id, title, link, published, author, summary)


def save_feed(title, link, subtitle, generator, articles):
    """Save a new subscription and its articles together; return its ID."""
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = get_feed_id(link)
        if existing is not None:
            return existing
        feed_id = _insert_feed(db, title, link, subtitle, generator)
        for article in articles:
            _insert_article(db, feed_id, **article)
        return feed_id


def replace_articles(feed_id, articles):
    db = get_db()
    with db:
        db.execute("DELETE FROM articles WHERE feed_id = ?", (feed_id,))
        for article in articles:
            _insert_article(db, feed_id, **article)


def get_articles(feed_id):
    rows = get_db().execute("""SELECT title, link, published, author, summary
        FROM articles WHERE feed_id = ? ORDER BY id""", (feed_id,))
    return [dict(row) for row in rows]


def list_feeds():
    return [dict(row) for row in get_db().execute("SELECT * FROM feeds ORDER BY id")]


def get_feed_by_id(feed_id):
    row = get_db().execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    return dict(row) if row else None


def delete_feed(feed_id):
    db = get_db()
    with db:
        return db.execute("DELETE FROM feeds WHERE id = ?", (feed_id,)).rowcount > 0


def delete_articles_by_feed(feed_id):
    db = get_db()
    with db:
        db.execute("DELETE FROM articles WHERE feed_id = ?", (feed_id,))


def update_metadata(feed_id, title, subtitle, generator):
    db = get_db()
    with db:
        db.execute("UPDATE feeds SET title = ?, subtitle = ?, generator = ? WHERE id = ?",
                   (title, subtitle, generator, feed_id))


def prompt_delete_feed():
    for feed in list_feeds():
        print(f"{feed['id']}: {feed['title']} {feed['link']}")
    try:
        delete_feed(int(input("Enter the feed ID to delete: ").strip()))
    except ValueError:
        print("Please enter a valid numerical ID.")
