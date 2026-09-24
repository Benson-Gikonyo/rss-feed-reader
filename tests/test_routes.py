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

    def post(self, path, data=None, **kwargs):
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        return self.client.post(path, data={**(data or {}), "csrf_token": token}, **kwargs)

    def test_add_view_edit_refresh_delete(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT):
            result = self.post("/add_feed", data={"feed_url": SOURCE}, follow_redirects=True)
            self.assertIn(b"Feed added successfully", result.data)
            with self.app.app_context():
                feed_id = db.get_feed_id(SOURCE)
            self.assertEqual(self.client.get(f"/feed/{feed_id}").status_code, 200)
            self.assertEqual(self.client.get(f"/edit_feed/{feed_id}").status_code, 200)
            self.post(f"/edit_feed/{feed_id}", data={"title": "Edited"})
            result = self.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
            self.assertIn(b"Feed refreshed successfully", result.data)
            self.post(f"/delete_rss_feed/{feed_id}")
            with self.app.app_context():
                self.assertIsNone(db.get_feed_by_id(feed_id))

    def test_normalized_duplicate_does_not_fetch_again(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT) as fetch:
            self.post("/add_feed", data={"feed_url": SOURCE})
            result = self.post("/add_feed", data={"feed_url": "HTTPS://EXAMPLE.org:443/rss#x"}, follow_redirects=True)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn(b"already added", result.data)

    def test_failures_show_safe_messages_and_preserve_records(self):
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
            before = db.get_articles(feed_id)
        for error in (FeedTimeoutError("The feed server took too long to respond."), InvalidFeedError("Invalid feed.")):
            with self.subTest(error=error), patch("rss_reader.routes.fetch_feed", side_effect=error):
                result = self.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
                self.assertIn(str(error).encode(), result.data)
                with self.app.app_context():
                    self.assertEqual(db.get_articles(feed_id), before)

    def test_database_failure_does_not_report_success(self):
        with patch("rss_reader.routes.fetch_feed", return_value=RESULT), patch("rss_reader.routes.save_feed", side_effect=sqlite3.OperationalError("secret")):
            result = self.post("/add_feed", data={"feed_url": SOURCE}, follow_redirects=True)
        self.assertEqual(result.status_code, 503)
        self.assertIn(SOURCE.encode(), result.data)
        self.assertIn(b"Unable to save", result.data)
        self.assertNotIn(b"secret", result.data)
        self.assertNotIn(b"Feed added successfully", result.data)

    def test_304_message(self):
        with self.app.app_context():
            feed_id, _ = db.save_feed(RESULT)
        with patch("rss_reader.routes.fetch_feed", return_value=FetchResult(SOURCE, SOURCE, not_modified=True)):
            result = self.post(f"/refresh_feed/{feed_id}", follow_redirects=True)
        self.assertIn(b"already up to date", result.data)

    def test_missing_or_unsafe_form_url(self):
        with patch("rss_reader.routes.fetch_feed") as fetch:
            for data in ({}, {"feed_url": "file:///etc/passwd"}, {"feed_url": "https://user:secret@example.org/"}):
                result = self.post("/add_feed", data=data, follow_redirects=True)
                self.assertEqual(result.status_code, 400)
                self.assertNotIn(b"secret", result.data)
            fetch.assert_not_called()

    def seed(self, count=1):
        feed = Feed("Feed", articles=[Article(f"id-{i}", f"Article {i:02}", published_at="2026-09-24T10:00:00+00:00") for i in range(count)])
        with self.app.app_context():
            return db.save_feed(FetchResult(SOURCE, SOURCE, feed))[0]

    def test_all_mutations_require_matching_session_token(self):
        feed_id = self.seed()
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        for path in ("/add_feed", f"/edit_feed/{feed_id}", f"/refresh_feed/{feed_id}", f"/delete_rss_feed/{feed_id}"):
            for bad in (None, "wrong", "é"):
                with self.subTest(path=path, bad=bad), patch("rss_reader.routes.fetch_feed") as fetch:
                    response = self.client.post(path, data={} if bad is None else {"csrf_token": bad})
                    self.assertEqual(response.status_code, 400)
                    fetch.assert_not_called()
            other_client = self.app.test_client()
            self.assertEqual(other_client.post(path, data={"csrf_token": token}).status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.get_feed_by_id(feed_id)["title"], "Feed")
            self.assertEqual(len(db.get_articles(feed_id)), 1)

    def test_forms_have_tokens_and_single_flash_and_css(self):
        feed_id = self.seed()
        for path in ("/", f"/edit_feed/{feed_id}", f"/delete_rss_feed/{feed_id}"):
            response = self.client.get(path)
            self.assertIn(b'name="csrf_token"', response.data)
            self.assertEqual(response.data.count(b"bootstrap.min.css"), 1)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with self.client.session_transaction() as session:
            session["_flashes"] = [("success", "Exactly one message")]
        self.assertEqual(self.client.get("/").data.count(b"Exactly one message"), 1)

    def test_pagination_stable_order_and_sql_limits(self):
        feed_id = self.seed(12)
        queries = []
        with self.app.app_context():
            db.get_db().set_trace_callback(queries.append)
            first = self.client.get(f"/feed/{feed_id}?page=1")
            second = self.client.get(f"/feed/{feed_id}?page=2")
            third = self.client.get(f"/feed/{feed_id}?page=3")
        self.assertIn(b"Article 11", first.data)
        self.assertNotIn(b"Article 06", first.data)
        self.assertIn(b"Article 06", second.data)
        self.assertNotIn(b"Article 11", second.data)
        self.assertIn(b"Article 00", third.data)
        self.assertIn(b"Page 3 of 3", third.data)
        self.assertNotIn(b'rel="next"', third.data)
        selects = [query.upper() for query in queries if "SELECT * FROM ARTICLES" in query.upper()]
        self.assertEqual(len(selects), 3)
        self.assertTrue(all("LIMIT 5 OFFSET" in query for query in selects))

    def test_invalid_pages_and_missing_resources(self):
        feed_id = self.seed(0)
        self.assertIn(b"no articles yet", self.client.get(f"/feed/{feed_id}").data)
        for page in ("0", "-1", "abc", "1.5", ""):
            self.assertEqual(self.client.get(f"/feed/{feed_id}?page={page}").status_code, 400)
        for page in ("2", "99999999999999999999999999"):
            self.assertEqual(self.client.get(f"/feed/{feed_id}?page={page}").status_code, 404)
        for path in ("/feed/999", "/edit_feed/999", "/delete_rss_feed/999"):
            self.assertEqual(self.client.get(path).status_code, 404)
        for path in ("/edit_feed/999", "/delete_rss_feed/999", "/refresh_feed/999"):
            self.assertEqual(self.post(path).status_code, 404)

    def test_edit_validation_retains_input_and_optional_fields(self):
        feed_id = self.seed()
        response = self.post(f"/edit_feed/{feed_id}", data={"title": " ", "subtitle": "Keep this"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Keep this", response.data)
        self.assertIn(b'aria-invalid="true"', response.data)
        response = self.post(f"/edit_feed/{feed_id}", data={"title": "Changed"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.get_feed_by_id(feed_id)["subtitle"], "")

    def test_edit_and_delete_failures_are_logged_and_safe(self):
        feed_id = self.seed()
        for function, path, data in (
            ("update_metadata", f"/edit_feed/{feed_id}", {"title": "Keep my edit"}),
            ("delete_feed", f"/delete_rss_feed/{feed_id}", {}),
        ):
            with patch(f"rss_reader.routes.{function}", side_effect=sqlite3.OperationalError("secret detail")), self.assertLogs(self.app.logger, level="ERROR") as logs:
                response = self.post(path, data=data)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b"secret detail", response.data)
            self.assertNotIn("secret detail", " ".join(logs.output))
            if data:
                self.assertIn(b"Keep my edit", response.data)
        with self.app.app_context():
            self.assertEqual(db.get_feed_by_id(feed_id)["title"], "Feed")

    def test_delete_confirmation_get_does_not_delete(self):
        feed_id = self.seed()
        response = self.client.get(f"/delete_rss_feed/{feed_id}")
        self.assertIn(b"cannot be undone", response.data)
        with self.app.app_context():
            self.assertIsNotNone(db.get_feed_by_id(feed_id))
        self.post(f"/delete_rss_feed/{feed_id}")
        with self.app.app_context():
            self.assertIsNone(db.get_feed_by_id(feed_id))

    def test_home_read_failure_has_safe_503(self):
        with patch("rss_reader.routes.list_feeds", side_effect=sqlite3.OperationalError("secret detail")):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secret detail", response.data)

    def test_health_ready_missing_and_incomplete_database(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})
        self.assertNotIn("Set-Cookie", response.headers)
        missing = Path(self.temp.name) / "missing.db"
        self.app.config["DATABASE"] = str(missing)
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(missing.exists())
        with sqlite3.connect(missing) as connection:
            connection.execute("PRAGMA user_version = 2")
        self.assertEqual(self.client.get("/healthz").status_code, 503)
