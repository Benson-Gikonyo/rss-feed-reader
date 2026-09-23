import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from rss_reader import create_app, database as db
from rss_reader.models import Article, Feed, FetchResult

SOURCE = "https://example.org/rss"
ARTICLE = Article("story-1", "Article", "https://example.org/article", summary="Summary")
RESULT = FetchResult(SOURCE, SOURCE, Feed("Feed", "https://example.org/", articles=[ARTICLE]), etag='"v1"')


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "feeds.db"
        self.app = create_app({"TESTING": True, "DATABASE": str(self.path)})

    def initialize(self):
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_explicit_initialization_and_import(self):
        self.assertFalse(self.path.exists())
        root = str(Path(__file__).resolve().parents[1])
        subprocess.run([sys.executable, "-c",
                        f"import sys; sys.path.insert(0, {root!r}); import rss_reader.database; import main"],
                       cwd=self.temp.name, check=True)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.initialize()
        self.assertTrue(self.path.exists())

    def test_context_connection_isolation_and_close(self):
        self.initialize()
        with self.app.app_context():
            connection = db.get_db()
            self.assertIs(connection, db.get_db())
            db.save_feed(RESULT)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        other = create_app({"TESTING": True, "DATABASE": str(Path(self.temp.name) / "other.db")})
        with other.app_context():
            db.setup_database()
            self.assertEqual(db.list_feeds(), [])

    def test_crud_constraints_and_cascade(self):
        self.initialize()
        with self.app.app_context():
            feed_id, created = db.save_feed(RESULT)
            self.assertTrue(created)
            self.assertEqual(db.save_feed(RESULT), (feed_id, False))
            db.update_metadata(feed_id, "Edited", "Sub", "Gen")
            self.assertEqual(db.get_feed_by_id(feed_id)["subtitle"], "Sub")
            connection = db.get_db()
            invalid = [
                ("INSERT INTO feeds(source_url, title) VALUES (?, 'Duplicate')", (SOURCE,)),
                ("INSERT INTO feeds(source_url, title) VALUES ('other', NULL)", ()),
                ("INSERT INTO articles(feed_id, guid, title) VALUES (999, 'x', 'X')", ()),
                ("INSERT INTO articles(feed_id, guid, title) VALUES (?, 'story-1', 'X')", (feed_id,)),
                ("INSERT INTO articles(feed_id, guid, title) VALUES (?, NULL, 'X')", (feed_id,)),
            ]
            for sql, params in invalid:
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), connection:
                    connection.execute(sql, params)
            db.setup_database()
            self.assertEqual(len(db.get_articles(feed_id)), 1)
            self.assertTrue(db.delete_feed(feed_id))
            self.assertEqual(db.get_articles(feed_id), [])
            self.assertIsNone(db.get_feed_by_id(feed_id))

    def test_upsert_retains_older_articles_and_updates_same_guid(self):
        self.initialize()
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            old_id = db.get_articles(feed_id)[0]["id"]
            newer = Article("story-2", "New story")
            updated = replace(ARTICLE, title="Updated")
            result = replace(RESULT, feed=Feed("New title", articles=[updated, newer, newer]))
            db.save_feed(result, feed_id=feed_id)
            self.assertEqual(len(db.get_articles(feed_id)), 2)
            first = next(a for a in db.get_articles(feed_id) if a["guid"] == "story-1")
            self.assertEqual((first["id"], first["title"]), (old_id, "Updated"))
            db.save_feed(replace(RESULT, feed=Feed("Empty now")), feed_id=feed_id)
            self.assertEqual(len(db.get_articles(feed_id)), 2)
            self.assertEqual(db.get_feed_by_id(feed_id)["title"], "Empty now")

    def test_failed_writes_roll_back_metadata_articles_and_cache(self):
        self.initialize()
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            before = db.get_feed_by_id(feed_id)
            articles = db.get_articles(feed_id)
            bad = replace(RESULT, etag='"v2"', feed=Feed("Changed", articles=[replace(ARTICLE, title="Changed"), Article("bad", None)]))
            with self.assertRaises(sqlite3.IntegrityError):
                db.save_feed(bad, feed_id=feed_id)
            self.assertEqual(db.get_feed_by_id(feed_id), before)
            self.assertEqual(db.get_articles(feed_id), articles)
            with self.assertRaises(sqlite3.IntegrityError):
                db.save_feed(replace(bad, source_url="https://other.org/rss"))
            self.assertIsNone(db.get_feed_id("https://other.org/rss"))

    def test_304_preserves_content_and_cache_and_updates_fetch_time(self):
        self.initialize()
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            with db.get_db():
                db.get_db().execute("UPDATE feeds SET last_fetched_at='old' WHERE id=?", (feed_id,))
            articles = db.get_articles(feed_id)
            db.save_feed(FetchResult(SOURCE, SOURCE, not_modified=True), feed_id=feed_id)
            self.assertEqual(db.get_articles(feed_id), articles)
            feed = db.get_feed_by_id(feed_id)
            self.assertEqual(feed["etag"], '"v1"')
            self.assertNotEqual(feed["last_fetched_at"], "old")

    def test_successful_fetch_without_validators_clears_stale_cache(self):
        self.initialize()
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            db.save_feed(replace(RESULT, etag=None), feed_id=feed_id)
            self.assertIsNone(db.get_feed_by_id(feed_id)["etag"])

    def test_two_connections_add_only_one_feed(self):
        self.initialize()
        barrier = threading.Barrier(2)
        def add():
            with self.app.app_context():
                barrier.wait(timeout=5)
                return db.save_feed(RESULT)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(add) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(created for _, created in results), [False, True])

    def test_reinitialization_leaves_existing_data_unchanged(self):
        self.initialize()
        with self.app.app_context():
            db.save_feed(RESULT)
            before = list(db.get_db().iterdump())
        self.initialize()
        with self.app.app_context():
            self.assertEqual(list(db.get_db().iterdump()), before)
            self.assertEqual(db.get_db().execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_initialization_does_not_overwrite_an_unrecognized_database(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE notes (content TEXT)")
            connection.execute("INSERT INTO notes VALUES ('keep me')")
            before = list(connection.iterdump())
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("does not replace", result.output)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(list(connection.iterdump()), before)


if __name__ == "__main__":
    unittest.main()
