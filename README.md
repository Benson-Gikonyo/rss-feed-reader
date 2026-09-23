# DevProjects - RSS feed reader in terminal

This is an open source project from [DevProjects](http://www.codementor.io/projects). Feedback and questions are welcome!
Find the project requirements here: [RSS feed reader in terminal](https://www.codementor.io/projects/tool/rss-feed-reader-in-terminal-atx32jp82q)

## Tech/framework used
Built with Flask, Sqlite and  bootstrap

## Screenshots and demo
Screenshots of your app and/or a link to your live demo
![Screenshot (45)](https://github.com/user-attachments/assets/0d6f751d-b0a3-40c5-a487-2f808993de6d)
![Screenshot (46)](https://github.com/user-attachments/assets/db8c0b89-9288-485c-b087-284a402ea176)
![Screenshot (47)](https://github.com/user-attachments/assets/754317b8-e449-407d-87e8-c689feee3713)


## Installation
clone the repository to your local machine
create a virtual enviroment:

```
python3 -m venv venv
```

```
source venv/bin/activate
```
install the requirements:

```
pip install -r requirements.txt
```
create your local environment file and replace the placeholder secret:

```
cp .env.example .env
```
Initialize the database **once per database**, before the first run:

```bash
flask --app rss_reader:create_app init-db
```

After this command succeeds, you do not need to run it again for normal app
starts or restarts. Starting the app does not automatically initialize the
database. Run the command once whenever you set up a new database. Re-running
it against an already initialized database leaves its schema and data unchanged.

A fresh clone contains no database or saved subscriptions. `init-db` creates an
empty database using the current schema, ready for you to add feeds in the app.
It does not import old records or upgrade existing schemas. If the configured
file contains an incompatible database, initialization stops without changing it.

The database is stored at `instance/rss_feeds.db` by default and is excluded from
Git. Connections use the app's `DATABASE` configuration and close when the
application context ends. Tests use temporary databases instead.

Database operations live in `rss_reader/database.py`, with table definitions in
`rss_reader/schema.sql`. Required fields and database-level uniqueness protect
subscriptions (`source_url`) and articles (`feed_id`, `guid`).

Run the application:

```
python3 app.py
```




## License
[MIT](https://choosealicense.com/licenses/mit/)


## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and mocked feeds; they do not touch local feed data.

## Fetching, parsing, and refresh behavior

Both Flask routes and the optional terminal menu (`python main.py`) use
`rss_reader/feed_service.py`. Parsing receives downloaded bytes and returns
normalized `Feed`, `Article`, and `FetchResult` values. It never writes to SQLite.

- `url_safety.py` accepts HTTP/HTTPS URLs without credentials, normalizes hosts
  and default ports, resolves the hostname, and checks every IPv4/IPv6 answer.
  Non-public, loopback, link-local, multicast, reserved, and unspecified addresses
  are rejected. Redirect destinations receive the same checks.
- Redirects are followed manually, up to three hops. Redirect bodies are not
  downloaded. Ambient proxies and `.netrc` credentials are disabled for fetches.
- Requests use separate 3-second connection and 10-second read timeouts, a clear
  user agent, and streamed downloads limited to 2,000,000 decoded bytes.
  Declared oversize responses are rejected before reading. These timeouts are
  per connection/read inactivity, not a strict total deadline; OS DNS resolution
  and slow trickle responses can take longer.
- XML, common feed types, plain text, generic binary, and HTML-labelled responses
  are accepted for parsing to tolerate misconfigured servers. The body must still
  be recognizable RSS/Atom; ordinary HTML pages and unsuitable media are rejected.
- Valid empty feeds are accepted. Recoverable malformed feeds with entries produce
  a warning; unreadable feeds produce safe user-facing errors. Optional metadata
  has defaults, invalid dates become NULL, and displayed links allow HTTP/HTTPS only.
- Article identity uses the supplied GUID/Atom ID, then a normalized article URL.
  If neither exists, a content hash is used. That last fallback is best effort:
  editing an unidentifiable article can create a new record.
- Refresh updates feed metadata and upserts articles in one transaction. Older
  articles remain even when absent from the newest response. Failures roll back
  metadata, articles, and cache fields together.
- ETag and Last-Modified are saved and sent only to the matching fetched URL.
  HTTP 304 updates `last_fetched_at` without changing articles or feed metadata.
  A successful response without validators clears old validators.

**Security boundary:** DNS is checked before Requests establishes its connection;
this implementation does not pin that connection to the validated IP. DNS rebinding
remains possible. Use network-level egress restrictions blocking internal and
metadata destinations before exposing arbitrary public URL submissions. This is
SSRF-aware validation, not a complete SSRF sandbox.

Expected failures are logged by operation/category (and feed ID for refreshes)
with safe failure reasons, without raw URLs, response bodies, credentials, or raw
network exception messages. Recoverable
parse warnings include the parser exception type.

Configuration is documented in `.env.example`. `DATABASE_PATH`, if relative, is
resolved from the working directory. Its parent must already exist. The default
without an override is the Flask instance directory. Fetch limit and timeout
settings can also be overridden through `create_app` for tests.

Tests include small RSS/Atom fixtures, mocked HTTP adapters, concurrent SQLite
writers, non-destructive initialization, atomic rollback, safe URL handling, redirect
limits, timeouts, size limits, conditional requests, and web/terminal integration.
They make no live network requests.
