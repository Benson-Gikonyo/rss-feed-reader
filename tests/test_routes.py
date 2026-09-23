import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rss_reader import create_app, database as db
from rss_reader.errors import FeedTimeoutError, InvalidFeedError
from rss_reader.models import Article, Feed, FetchResult

SOURCE = "https://example.org/rss"
RESULT = FetchResult(SOURCE, SOURCE, Feed("Feed", articles=[Article("one", "Story")]))


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.temp.name) / "test.db")})
        with self.app.app_context():
            db.setup_database()
        self.client = self.app.test_client()

    def test_add_view_edit_refresh_delete(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT):
            result = self.client.post("/add_feed", data={"feed_url": SOURCE}, follow_redirects=True)
            self.assertIn(b"Feed added successfully", result.data)
            with self.app.app_context():
                feed_id = db.get_feed_id(SOURCE)
            self.assertEqual(self.client.get(f"/feed/{feed_id}").status_code, 200)
            self.assertEqual(self.client.get(f"/edit_feed/{feed_id}").status_code, 200)
            self.client.post(f"/edit_feed/{feed_id}", data={"title": "Edited"})
            result = self.client.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
            self.assertIn(b"Feed refreshed successfully", result.data)
            self.client.post(f"/delete_rss_feed/{feed_id}")
            with self.app.app_context():
                self.assertIsNone(db.get_feed_by_id(feed_id))

    def test_normalized_duplicate_does_not_fetch_again(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT) as fetch:
            self.client.post("/add_feed", data={"feed_url": SOURCE})
            result = self.client.post("/add_feed", data={"feed_url": "HTTPS://EXAMPLE.org:443/rss#x"}, follow_redirects=True)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn(b"already added", result.data)

    def test_failures_show_safe_messages_and_preserve_records(self):
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            before = db.get_articles(feed_id)
        for error in (FeedTimeoutError("The feed server took too long to respond."), InvalidFeedError("Invalid feed.")):
            with self.subTest(error=error), patch("rss_reader.routes.fetch_feed", side_effect=error):
                result = self.client.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
                self.assertIn(str(error).encode(), result.data)
                with self.app.app_context():
                    self.assertEqual(db.get_articles(feed_id), before)

    def test_database_failure_does_not_report_success(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT), patch("rss_reader.routes.save_feed", side_effect=sqlite3.OperationalError("secret")):
            result = self.client.post("/add_feed", data={"feed_url": SOURCE}, follow_redirects=True)
        self.assertIn(b"Unable to save", result.data)
        self.assertNotIn(b"secret", result.data)
        self.assertNotIn(b"Feed added successfully", result.data)

    def test_304_message(self):
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
        with patch("rss_reader.routes.fetch_feed", return_value=FetchResult(SOURCE, SOURCE, not_modified=True)):
            result = self.client.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
        self.assertIn(b"already up to date", result.data)

    def test_missing_or_unsafe_form_url(self):
        with patch("rss_reader.routes.fetch_feed") as fetch:
            for data in ({}, {"feed_url": "file:///etc/passwd"}, {"feed_url": "https://user:secret@example.org/"}):
                result = self.client.post("/add_feed", data=data, follow_redirects=True)
                self.assertEqual(result.status_code, 200)
                self.assertNotIn(b"secret", result.data)
            fetch.assert_not_called()

    def test_terminal_uses_shared_fetcher(self):
        from main import main_menu
        with self.app.app_context(), patch("builtins.input", side_effect=["1", SOURCE, "5"]), patch("builtins.print"), patch("main.fetch_feed", return_value=RESULT) as fetch:
            main_menu()
            fetch.assert_called_once_with(SOURCE)
            self.assertIsNotNone(db.get_feed_id(SOURCE))
