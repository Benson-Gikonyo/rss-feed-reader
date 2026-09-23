"""Fetch bounded responses, then parse bytes without persistence side effects."""
import calendar
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import requests
from flask import current_app
from urllib3.exceptions import ReadTimeoutError

from .errors import FeedFetchError, FeedTimeoutError, InvalidFeedError, UnsafeFeedURLError
from .models import Article, Feed, FetchResult, article_identity
from .url_safety import normalize_url, validate_url

logger = logging.getLogger(__name__)
REDIRECTS = {301, 302, 303, 307, 308}


class FeedSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs):
        # Requests otherwise consumes a redirect body while preparing response.next,
        # even with allow_redirects=False. We follow redirects ourselves, without it.
        return iter(())


def safe_link(value, base):
    if not value:
        return None
    try:
        return normalize_url(urljoin(base, value))
    except (UnsafeFeedURLError, ValueError):
        return None


def parse_feed(body, base_url):
    parsed = feedparser.parse(body, response_headers={"content-location": base_url, "content-type": "application/xml"})
    if not parsed.get("version") or not parsed.get("feed"):
        raise InvalidFeedError("The response is not a readable RSS or Atom feed.")
    if parsed.get("bozo") and not parsed.entries:
        raise InvalidFeedError("The feed is malformed and has no recoverable articles.")
    if parsed.get("bozo"):
        logger.warning("Accepted recoverable feed parse error: %s",
                       type(parsed.get("bozo_exception")).__name__)
    articles = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip() or "Untitled article"
        url = safe_link(entry.get("link"), base_url)
        author = entry.get("author") or None
        content = entry.get("content") or []
        summary = (content[0].get("value") if content else entry.get("summary")) or ""
        published_at = None
        date = entry.get("published_parsed") or dict.get(entry, "updated_parsed")
        if date:
            try:
                published_at = datetime.fromtimestamp(calendar.timegm(date), timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        articles.append(Article(
            guid=article_identity(entry.get("id"), url, title, author, summary),
            title=title, url=url, published_at=published_at, author=author, summary=summary,
        ))
    return Feed(
        title=(parsed.feed.get("title") or "").strip() or "Untitled feed",
        site_url=safe_link(parsed.feed.get("link"), base_url),
        subtitle=parsed.feed.get("subtitle") or "",
        generator=parsed.feed.get("generator") or "",
        articles=articles,
    )


def _is_read_timeout(error):
    return any(isinstance(arg, ReadTimeoutError) for arg in error.args)


def fetch_feed(url, *, cached=None):
    config = current_app.config
    source_url = normalize_url(url)
    target = source_url
    seen = set()
    headers = {"User-Agent": "RSSFeedReader/1.0", "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1"}
    try:
        with FeedSession() as session:
            # Ignore ambient proxies and .netrc credentials for user-submitted URLs.
            session.trust_env = False
            for hop in range(config["MAX_FEED_REDIRECTS"] + 1):
                target = validate_url(target)
                if target in seen:
                    raise FeedFetchError("The feed redirected in a loop.")
                seen.add(target)
                request_headers = dict(headers)
                if cached and cached.get("fetch_url") == target:
                    if cached.get("etag"):
                        request_headers["If-None-Match"] = cached["etag"]
                    if cached.get("last_modified"):
                        request_headers["If-Modified-Since"] = cached["last_modified"]
                with session.get(
                    target, headers=request_headers, stream=True, allow_redirects=False,
                    timeout=(config["FETCH_CONNECT_TIMEOUT"], config["FETCH_READ_TIMEOUT"]),
                ) as response:
                    if response.status_code in REDIRECTS:
                        location = response.headers.get("Location")
                        if not location or hop == config["MAX_FEED_REDIRECTS"]:
                            raise FeedFetchError("The feed has an invalid or excessive redirect chain.")
                        target = urljoin(target, location)
                        continue
                    if response.status_code == 304:
                        if not any(k in request_headers for k in ("If-None-Match", "If-Modified-Since")):
                            raise FeedFetchError("The server returned an unexpected unchanged response.")
                        return FetchResult(source_url, target, not_modified=True,
                                           etag=response.headers.get("ETag"),
                                           last_modified=response.headers.get("Last-Modified"))
                    if response.status_code != 200:
                        raise FeedFetchError(f"The feed server returned HTTP {response.status_code}.")
                    media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    allowed = {"", "application/xml", "text/xml", "application/rss+xml", "application/atom+xml", "text/plain", "application/octet-stream", "text/html"}
                    if media_type not in allowed and not media_type.endswith("+xml"):
                        raise InvalidFeedError("The server did not return a supported feed content type.")
                    limit = config["MAX_FEED_BYTES"]
                    length = response.headers.get("Content-Length")
                    if length:
                        try:
                            if int(length) > limit:
                                raise FeedFetchError("The feed exceeds the download size limit.")
                        except ValueError:
                            pass
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=8192):
                        if len(body) + len(chunk) > limit:
                            raise FeedFetchError("The feed exceeds the download size limit.")
                        body.extend(chunk)
                    return FetchResult(source_url, target, parse_feed(bytes(body), target),
                                       etag=response.headers.get("ETag"),
                                       last_modified=response.headers.get("Last-Modified"))
    except requests.Timeout:
        raise FeedTimeoutError("The feed server took too long to respond.") from None
    except requests.ConnectionError as error:
        if _is_read_timeout(error):
            raise FeedTimeoutError("The feed server took too long to respond.") from None
        raise FeedFetchError("Unable to connect to the feed server.") from None
    except requests.RequestException:
        raise FeedFetchError("Unable to download the feed.") from None
    except ValueError:
        raise FeedFetchError("The server returned an invalid redirect URL.") from None
