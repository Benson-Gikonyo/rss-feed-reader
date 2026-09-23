"""URL normalization and preflight destination checks (not DNS pinning)."""
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from .errors import FeedFetchError, UnsafeFeedURLError


def normalize_url(url):
    """Normalize identity without network access, reject ambiguous authority syntax."""
    try:
        if not isinstance(url, str) or re.search(r"[\s\x00-\x1f\x7f\\]", url):
            raise ValueError
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.rstrip(".").lower()
        if "%" in host:  # Includes scoped IPv6 and percent-encoded authority tricks.
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
            host = address.compressed
            if address.version == 6:
                host = f"[{host}]"
        except ValueError:
            host = host.encode("idna").decode("ascii")
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError
        port = parsed.port
        if port == 0:
            raise ValueError
        scheme = parsed.scheme.lower()
        authority = host
        if port is not None and port != (443 if scheme == "https" else 80):
            authority += f":{port}"
        return urlunsplit((scheme, authority, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError, AttributeError):
        raise UnsafeFeedURLError("Enter an HTTP or HTTPS URL without embedded credentials.") from None


def validate_url(url):
    normalized = normalize_url(url)
    parsed = urlsplit(normalized)
    host = parsed.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeFeedURLError("Feeds must use a public internet address.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                       type=socket.SOCK_STREAM)
    except OSError:
        raise FeedFetchError("Unable to resolve the feed's hostname.") from None
    if not addresses:
        raise FeedFetchError("Unable to resolve the feed's hostname.")
    for info in addresses:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            raise UnsafeFeedURLError("The feed hostname returned an invalid address.") from None
        mapped = getattr(address, "ipv4_mapped", None)
        if (not address.is_global or address.is_multicast or address.is_reserved
                or address.is_loopback or address.is_link_local or address.is_unspecified
                or (mapped is not None and not mapped.is_global)):
            raise UnsafeFeedURLError("Feeds must use a public internet address.")
    return normalized
