import socket
import unittest
from unittest.mock import patch

from rss_reader.errors import FeedFetchError, UnsafeFeedURLError
from rss_reader.url_safety import normalize_url, validate_url


def addresses(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ips]


class URLSafetyTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_url("HTTPS://EXAMPLE.org.:443/feed#part"), "https://example.org/feed")
        self.assertEqual(normalize_url("http://example.org:80"), "http://example.org/")
        self.assertEqual(normalize_url("https://[2606:4700:4700::1111]:443/rss"), "https://[2606:4700:4700::1111]/rss")
        self.assertEqual(normalize_url("https://bücher.example/rss"), "https://xn--bcher-kva.example/rss")

    def test_rejects_bad_url_syntax(self):
        for url in ("file:///etc/passwd", "ftp://example.org/rss", "https:///rss", "https://user:password@example.org/", "https://user@example.org/", "https://example.org:99999/", "https://example.org:0/", "https://exa mple.org/", "https://example.org\\@localhost/", "https://[fe80::1%25eth0]/", "https://example.org/\n", "https://%31%32%37.0.0.1/"):
            with self.subTest(url=url), self.assertRaises(UnsafeFeedURLError):
                normalize_url(url)

    def test_rejects_localhost_without_dns(self):
        for host in ("localhost", "LOCALHOST.", "service.localhost"):
            with patch("rss_reader.url_safety.socket.getaddrinfo") as dns:
                with self.assertRaises(UnsafeFeedURLError):
                    validate_url(f"http://{host}/")
                dns.assert_not_called()

    def test_rejects_nonpublic_ipv4_and_ipv6(self):
        for ip in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "240.0.0.1", "100.64.0.1", "::1", "::", "fc00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1"):
            with self.subTest(ip=ip), patch("rss_reader.url_safety.socket.getaddrinfo", return_value=addresses(ip)):
                with self.assertRaises(UnsafeFeedURLError):
                    validate_url("https://example.org/rss")

    def test_checks_all_dns_answers(self):
        with patch("rss_reader.url_safety.socket.getaddrinfo", return_value=addresses("8.8.8.8", "10.0.0.1")):
            with self.assertRaises(UnsafeFeedURLError):
                validate_url("https://example.org/rss")

    def test_public_ipv4_ipv6_and_dns_failure(self):
        with patch("rss_reader.url_safety.socket.getaddrinfo", return_value=addresses("8.8.8.8", "2606:4700:4700::1111")):
            self.assertEqual(validate_url("https://example.org/rss"), "https://example.org/rss")
        with patch("rss_reader.url_safety.socket.getaddrinfo", side_effect=socket.gaierror("private detail")):
            with self.assertRaisesRegex(FeedFetchError, "Unable to resolve"):
                validate_url("https://example.org/rss")

    def test_empty_and_invalid_dns_answers_fail_closed(self):
        for answers in ([], addresses("not-an-ip")):
            with self.subTest(answers=answers), patch("rss_reader.url_safety.socket.getaddrinfo", return_value=answers):
                with self.assertRaises(FeedFetchError):
                    validate_url("https://example.org/rss")
