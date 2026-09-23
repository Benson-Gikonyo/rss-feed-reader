"""Normalized values passed between fetching and persistence."""
from dataclasses import dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class Article:
    guid: str
    title: str
    url: str | None = None
    published_at: str | None = None
    author: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class Feed:
    title: str
    site_url: str | None = None
    subtitle: str = ""
    generator: str = ""
    articles: list[Article] = field(default_factory=list)


@dataclass(frozen=True)
class FetchResult:
    source_url: str
    fetch_url: str
    feed: Feed | None = None
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None


def article_identity(guid, url, title, author, summary):
    if guid and str(guid).strip():
        return str(guid).strip()
    if url:
        return "url:" + url
    # No GUID or URL: content identity is best effort, documented in README.
    payload = json.dumps([title, author, summary], ensure_ascii=False).encode()
    return "content:" + hashlib.sha256(payload).hexdigest()

