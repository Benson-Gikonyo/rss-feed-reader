import os
import unittest
from unittest.mock import patch

from rss_reader import create_app


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch("rss_reader.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)

    def test_production_requires_secret(self):
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY is required"):
            create_app()

    def test_test_secret_is_only_a_fallback(self):
        self.assertEqual(create_app({"TESTING": True}).secret_key, "testing-only-secret")
        self.assertEqual(create_app({"TESTING": True, "SECRET_KEY": "explicit"}).secret_key, "explicit")
        with patch.dict(os.environ, {"SECRET_KEY": "environment-secret"}):
            self.assertEqual(create_app().secret_key, "environment-secret")

    def test_environment_settings_and_explicit_overrides(self):
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret", "DATABASE_PATH": "/tmp/config-test-unused.db",
            "FETCH_CONNECT_TIMEOUT": "1.5", "FETCH_READ_TIMEOUT": "4",
            "MAX_FEED_BYTES": "1000", "MAX_FEED_REDIRECTS": "0",
        }):
            app = create_app({"FETCH_READ_TIMEOUT": 7})
        self.assertEqual(app.config["DATABASE"], "/tmp/config-test-unused.db")
        self.assertEqual(app.config["FETCH_CONNECT_TIMEOUT"], 1.5)
        self.assertEqual(app.config["FETCH_READ_TIMEOUT"], 7)
        self.assertEqual(app.config["MAX_FEED_BYTES"], 1000)
        self.assertEqual(app.config["MAX_FEED_REDIRECTS"], 0)

    def test_invalid_fetch_limits_fail_at_startup(self):
        for setting in ("FETCH_CONNECT_TIMEOUT", "FETCH_READ_TIMEOUT", "MAX_FEED_BYTES"):
            for value in (0, -1, float("inf"), float("nan")):
                with self.subTest(setting=setting, value=value):
                    with self.assertRaisesRegex(ValueError, setting):
                        create_app({"TESTING": True, setting: value})
        with self.assertRaisesRegex(ValueError, "MAX_FEED_REDIRECTS"):
            create_app({"TESTING": True, "MAX_FEED_REDIRECTS": -1})
