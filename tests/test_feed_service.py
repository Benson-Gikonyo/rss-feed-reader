import io
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from requests.adapters import BaseAdapter
from urllib3.exceptions import ReadTimeoutError

from rss_reader import create_app
from rss_reader.errors import FeedFetchError, FeedTimeoutError, InvalidFeedError, UnsafeFeedURLError
from rss_reader.feed_service import FeedSession, fetch_feed, parse_feed

FIXTURES = Path(__file__).with_name("fixtures")
SOURCE = "https://example.org/rss"
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]


class TrackingBody(io.BytesIO):
    def __init__(self, body, error=None):
        super().__init__(body)
        self.reads = 0
        self.error = error

    def release_conn(self):
        self.close()

    def read(self, *args):
        self.reads += 1
        if self.error:
            raise self.error
        return super().read(*args)


def response(body=b'', status=200, headers=None, error=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result.raw = TrackingBody(body, error)
    return result


class FakeAdapter(BaseAdapter):
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def send(self, request, **kwargs):
        self.calls.append((request, kwargs))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        result.request = request
        result.url = request.url
        return result

    def close(self):
        pass


class FeedServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "DATABASE": ":memory:"})
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        dns = patch("rss_reader.url_safety.socket.getaddrinfo", return_value=PUBLIC)
        dns.start()
        self.addCleanup(dns.stop)

    def session(self, *responses):
        adapter = FakeAdapter(responses)
        session = FeedSession()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        factory = patch("rss_reader.feed_service.FeedSession", return_value=session)
        factory.start()
        self.addCleanup(factory.stop)
        return adapter, session

    def test_rss_and_atom_normalization(self):
        rss = parse_feed((FIXTURES / "rss.xml").read_bytes(), SOURCE)
        self.assertEqual(rss.title, "Example feed")
        self.assertEqual(rss.site_url, "https://example.org/")
        self.assertEqual(rss.articles[0].guid, "story-1")
        self.assertEqual(rss.articles[0].published_at, "2026-09-23T10:00:00+00:00")
        self.assertEqual(rss.articles[1].guid, "url:https://example.org/two")
        self.assertIsNone(rss.articles[1].published_at)
        atom = parse_feed((FIXTURES / "atom.xml").read_bytes(), SOURCE)
        self.assertEqual(atom.articles[0].guid, "urn:story:1")
        self.assertEqual(atom.articles[0].url, "https://example.org/atom-story")

    def test_empty_recoverable_and_invalid_feeds(self):
        self.assertEqual(parse_feed((FIXTURES / "empty.xml").read_bytes(), SOURCE).articles, [])
        with self.assertLogs("rss_reader.feed_service", level="WARNING"):
            recovered = parse_feed((FIXTURES / "recoverable.xml").read_bytes(), SOURCE)
        self.assertEqual(len(recovered.articles), 1)
        for body in (b'<html><title>Web page</title></html>', b'garbage', b'<rss><channel><title>Broken'):
            with self.subTest(body=body), self.assertRaises(InvalidFeedError):
                parse_feed(body, SOURCE)

    def test_missing_fields_and_unsafe_links(self):
        body = b'<rss version="2.0"><channel><title>Feed</title><link>javascript:alert(1)</link><item><description>Text</description><link>javascript:alert(1)</link></item></channel></rss>'
        first = parse_feed(body, SOURCE)
        second = parse_feed(body, SOURCE)
        self.assertIsNone(first.site_url)
        article = first.articles[0]
        self.assertEqual(article.title, "Untitled article")
        self.assertIsNone(article.url)
        self.assertIsNone(article.author)
        self.assertIsNone(article.published_at)
        self.assertEqual(article.guid, second.articles[0].guid)
        self.assertTrue(article.guid.startswith("content:"))

    def test_fetch_uses_timeouts_user_agent_and_closes_response(self):
        result = response((FIXTURES / "rss.xml").read_bytes(), headers={"Content-Type": "text/plain", "ETag": '"v1"'})
        adapter, session = self.session(result)
        parsed = fetch_feed(SOURCE)
        self.assertEqual(parsed.source_url, SOURCE)
        self.assertEqual(parsed.etag, '"v1"')
        request, kwargs = adapter.calls[0]
        self.assertEqual(kwargs["timeout"], (3.0, 10.0))
        self.assertTrue(kwargs["stream"])
        self.assertEqual(request.headers["User-Agent"], "RSSFeedReader/1.0")
        self.assertFalse(session.trust_env)
        self.assertTrue(result.raw.closed)

    def test_redirect_body_not_read_and_relative_location_validated(self):
        redirect = response(b'not read', 302, {"Location": "/actual"})
        final = response((FIXTURES / "rss.xml").read_bytes())
        adapter, _ = self.session(redirect, final)
        result = fetch_feed(SOURCE)
        self.assertEqual(result.source_url, SOURCE)
        self.assertEqual(result.fetch_url, "https://example.org/actual")
        self.assertEqual(redirect.raw.reads, 0)
        self.assertTrue(redirect.raw.closed)
        self.assertEqual(len(adapter.calls), 2)

    def test_private_redirect_is_not_requested(self):
        adapter, _ = self.session(response(status=302, headers={"Location": "http://localhost/secret"}))
        with self.assertRaises(UnsafeFeedURLError):
            fetch_feed(SOURCE)
        self.assertEqual(len(adapter.calls), 1)

    def test_redirect_hostname_resolving_private_is_not_requested(self):
        adapter, _ = self.session(response(status=302, headers={"Location": "https://internal.example/rss"}))
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443))]
        with patch("rss_reader.url_safety.socket.getaddrinfo", side_effect=[PUBLIC, private]) as dns:
            with self.assertRaises(UnsafeFeedURLError):
                fetch_feed(SOURCE)
        self.assertEqual(dns.call_count, 2)
        self.assertEqual(len(adapter.calls), 1)

    def test_html_labelled_feed_accepted_but_html_body_rejected(self):
        adapter, _ = self.session(response((FIXTURES / "empty.xml").read_bytes(), headers={"Content-Type": "text/html"}))
        self.assertEqual(fetch_feed(SOURCE).feed.title, "Empty feed")

    def test_redirect_limit_and_loop(self):
        adapter, _ = self.session(*[response(status=302, headers={"Location": f"/hop{i}"}) for i in range(4)])
        with self.assertRaises(FeedFetchError):
            fetch_feed(SOURCE)
        self.assertEqual(len(adapter.calls), 4)

    def test_redirect_loop(self):
        adapter, _ = self.session(response(status=302, headers={"Location": SOURCE}))
        with self.assertRaisesRegex(FeedFetchError, "loop"):
            fetch_feed(SOURCE)
        self.assertEqual(len(adapter.calls), 1)

    def test_oversized_stream_closes_response(self):
        self.app.config["MAX_FEED_BYTES"] = 20
        oversized = response(b'x' * 30)
        self.session(oversized)
        with self.assertRaisesRegex(FeedFetchError, "size limit"):
            fetch_feed(SOURCE)
        self.assertTrue(oversized.raw.closed)

    def test_content_length_rejected_before_read(self):
        oversized = response(headers={"Content-Length": "2000001"})
        self.session(oversized)
        with self.assertRaises(FeedFetchError):
            fetch_feed(SOURCE)
        self.assertEqual(oversized.raw.reads, 0)

    def test_unsuitable_content_type_rejected(self):
        item = response(b'\x89PNG', headers={"Content-Type": "image/png"})
        self.session(item)
        with self.assertRaises(InvalidFeedError):
            fetch_feed(SOURCE)
        self.assertEqual(item.raw.reads, 0)

    def test_connection_timeout(self):
        self.session(requests.ConnectTimeout("secret URL"))
        with self.assertRaises(FeedTimeoutError) as raised:
            fetch_feed(SOURCE)
        self.assertNotIn("secret", str(raised.exception))

    def test_stream_read_timeout(self):
        item = response(error=requests.ConnectionError(ReadTimeoutError(None, SOURCE, "secret")))
        self.session(item)
        with self.assertRaises(FeedTimeoutError):
            fetch_feed(SOURCE)
        self.assertTrue(item.raw.closed)

    def test_connection_failure(self):
        self.session(requests.ConnectionError("secret"))
        with self.assertRaisesRegex(FeedFetchError, "Unable to connect"):
            fetch_feed(SOURCE)

    def test_http_error(self):
        item = response(status=503)
        self.session(item)
        with self.assertRaisesRegex(FeedFetchError, "HTTP 503"):
            fetch_feed(SOURCE)
        self.assertEqual(item.raw.reads, 0)

    def test_conditional_request_and_304(self):
        item = response(status=304, headers={"ETag": '"v2"'})
        adapter, _ = self.session(item)
        result = fetch_feed(SOURCE, cached={"fetch_url": SOURCE, "etag": '"v1"', "last_modified": "Wed, 23 Sep 2026 10:00:00 GMT"})
        self.assertTrue(result.not_modified)
        self.assertIsNone(result.feed)
        self.assertEqual(result.etag, '"v2"')
        self.assertEqual(adapter.calls[0][0].headers["If-None-Match"], '"v1"')
        self.assertIn("If-Modified-Since", adapter.calls[0][0].headers)
        self.assertEqual(item.raw.reads, 0)

    def test_cache_validators_only_sent_to_matching_url(self):
        adapter, _ = self.session(response(status=302, headers={"Location": "/other"}), response((FIXTURES / "empty.xml").read_bytes()))
        fetch_feed(SOURCE, cached={"fetch_url": SOURCE, "etag": '"v1"'})
        self.assertIn("If-None-Match", adapter.calls[0][0].headers)
        self.assertNotIn("If-None-Match", adapter.calls[1][0].headers)

    def test_unexpected_304_rejected(self):
        self.session(response(status=304))
        with self.assertRaises(FeedFetchError):
            fetch_feed(SOURCE)
