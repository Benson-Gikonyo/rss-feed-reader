import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database as db
from rss_reader import create_app


ARTICLE = dict(title="Article", link="https://example.org/article", published="today",
               author="Author", summary="Summary")


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "feeds.db"
        self.app = create_app({"TESTING": True, "DATABASE": str(self.path)})

    def initialize(self):
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, str(result.exception) or result.output)

    def test_explicit_initialization_and_import(self):
        self.assertFalse(self.path.exists())
        root = str(Path(__file__).resolve().parents[1])
        subprocess.run([sys.executable, "-c",
                        f"import sys; sys.path.insert(0, {root!r}); import database; import main"],
                       cwd=self.temp.name, check=True)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.initialize()
        self.assertTrue(self.path.exists())

    def test_context_connection_isolation_and_close(self):
        self.initialize()
        with self.app.app_context():
            connection = db.get_db()
            self.assertIs(connection, db.get_db())
            db.insert_feed("Feed", "url", "subtitle", "generator")
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        other = create_app({"TESTING": True, "DATABASE": str(Path(self.temp.name) / "other.db")})
        with other.app_context():
            db.setup_database()
            self.assertEqual(db.list_feeds(), [])

    def test_crud_duplicates_and_foreign_keys(self):
        self.initialize()
        with self.app.app_context():
            feed_id = db.save_feed("Feed", "url", "subtitle", "generator", [ARTICLE])
            self.assertEqual(db.save_feed("Feed", "url", "", "", [ARTICLE]), feed_id)
            self.assertEqual(len(db.get_articles(feed_id)), 1)
            db.update_metadata(feed_id, "Edited", "Sub", "Gen")
            self.assertEqual(db.get_feed_by_id(feed_id)["subtitle"], "Sub")
            with self.assertRaises(sqlite3.IntegrityError):
                db.insert_article(999, **ARTICLE)
            db.setup_database()
            self.assertEqual(len(db.get_articles(feed_id)), 1)
            self.assertTrue(db.delete_feed(feed_id))
            self.assertEqual(db.get_articles(feed_id), [])
            self.assertIsNone(db.get_feed_by_id(feed_id))

    def test_failed_writes_roll_back(self):
        self.initialize()
        with self.app.app_context():
            feed_id = db.save_feed("Feed", "url", "", "", [ARTICLE])
            with self.assertRaises(TypeError):
                db.replace_articles(feed_id, [ARTICLE, {"title": "broken"}])
            self.assertEqual(db.get_articles(feed_id), [ARTICLE])
            with self.assertRaises(TypeError):
                db.save_feed("Bad", "bad", "", "", [{"title": "broken"}])
            self.assertIsNone(db.get_feed_id("bad"))

    def legacy_database(self, orphan=False):
        with sqlite3.connect(self.path) as connection:
            connection.executescript('''
                CREATE TABLE feeds(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT, link TEXT, subtitle TEXT, generator TEXT);
                CREATE TABLE articles(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id INTEGER, title TEXT, link TEXT, published TEXT,
                    author TEXT, summary TEXT, FOREIGN KEY(feed_id) REFERENCES feed(id));
                INSERT INTO feeds VALUES(1, 'Feed', 'url', '', '');
            ''')
            connection.execute("INSERT INTO articles VALUES(1, ?, 'Article', 'url', '', '', '')",
                               (999 if orphan else 1,))

    def test_legacy_repair_preserves_data(self):
        self.legacy_database()
        self.initialize()
        with self.app.app_context():
            self.assertEqual(db.get_articles(1)[0]["title"], "Article")
            self.assertEqual(db.get_db().execute("PRAGMA foreign_key_check").fetchall(), [])
            db.delete_feed(1)
            self.assertEqual(db.get_articles(1), [])

    def test_invalid_legacy_repair_rolls_back(self):
        self.legacy_database(orphan=True)
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertNotEqual(result.exit_code, 0)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT feed_id FROM articles").fetchone()[0], 999)
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='articles_repaired'").fetchone())

    def test_add_refresh_and_delete_routes(self):
        self.initialize()
        parsed = ("Feed", "https://example.org/rss", "Subtitle", "Generator", [ARTICLE])
        client = self.app.test_client()
        with patch("rss_reader.routes.parse_url", return_value=parsed):
            self.assertEqual(client.post("/add_feed", data={"feed_url": parsed[1]}).status_code, 302)
            with self.app.app_context():
                feed_id = db.get_feed_id(parsed[1])
            self.assertEqual(client.get(f"/feed/{feed_id}").status_code, 200)
            self.assertEqual(client.post(f"/refresh_feed/{feed_id}").status_code, 302)
            with self.app.app_context():
                self.assertEqual(db.get_articles(feed_id), [ARTICLE])
        self.assertEqual(client.post(f"/delete_rss_feed/{feed_id}").status_code, 302)
        self.assertEqual(client.get("/").status_code, 200)

    def test_parser_is_read_only_and_keeps_feed_title_and_url(self):
        from feedparser import FeedParserDict
        from main import parse_url
        resource = FeedParserDict(feed=FeedParserDict(title="Feed", link="https://example.org"),
                                  entries=[FeedParserDict(ARTICLE)] * 8)
        with patch("main.feedparser.parse", return_value=resource):
            parsed = parse_url("https://example.org/rss")
        self.assertEqual(parsed[:2], ("Feed", "https://example.org/rss"))
        self.assertEqual(len(parsed[4]), 8)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
