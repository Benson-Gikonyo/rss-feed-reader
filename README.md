# Flask RSS/Atom Feed Reader

[![CI tests](https://github.com/Benson-Gikonyo/rss-feed-reader/actions/workflows/tests.yml/badge.svg)](https://github.com/Benson-Gikonyo/rss-feed-reader/actions/workflows/tests.yml)

A Flask RSS/Atom reader with persistent subscriptions, SSRF-aware feed fetching,
transactional refreshes, search, and article pagination. Add, read, edit, refresh,
and delete feeds through the web interface.

This project began with the [DevProjects terminal RSS-reader brief](https://www.codementor.io/projects/tool/rss-feed-reader-in-terminal-atx32jp82q)
and has evolved into a Flask web application. The interactive terminal menu has
been removed; Flask's `init-db` command remains available for database setup.


## Tech/framework used
Built with Flask, SQLite, and Bootstrap.

## Screenshots and demo

[Live demo](https://rss-feed-reader-zdnl.onrender.com/)

Adding a Feed: <img width="1366" height="768" alt="Feed Added Successfully" src="https://github.com/user-attachments/assets/a5758561-f827-4821-a6a7-923e3988679c" />

Viewing articles: <img width="1366" height="768" alt="Viewing Articles" src="https://github.com/user-attachments/assets/83c9907e-88ad-4945-8084-ed8952b9a14e" />

Editing a Feed: <img width="1366" height="768" alt="Editing a feed" src="https://github.com/user-attachments/assets/78e5dcf6-1fd3-4c64-a9aa-827acabeb540" />

Deleting a Feed: <img width="1366" height="768" alt="Deleting a Feed" src="https://github.com/user-attachments/assets/730729b7-bec9-4dc6-8e24-155f5d65bde2" />

Successful Deletion: <img width="1366" height="768" alt="Successful deletion" src="https://github.com/user-attachments/assets/a632dd89-11ba-4745-98ee-ed90a7cc6496" />

Refreshing a Feed: <img width="1366" height="768" alt="Refreshing a Feed" src="https://github.com/user-attachments/assets/5ff1e34a-4e00-4923-819a-a903cef61387" />


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

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.




## License
[MIT](https://choosealicense.com/licenses/mit/)


## Tests

```bash
python -m unittest discover -s tests -v
```

The suite uses Python's built-in `unittest`; no additional test dependencies are
needed after installing `requirements.txt`. Tests use temporary databases and
mocked HTTP/DNS responses; they do not touch local feed data or fetch live feeds.
Startup-configuration tests isolate environment variables and disable `.env`
loading so they can verify the missing-secret behavior reliably.

Coverage includes:

- Startup secrets, environment overrides, and invalid fetch limits.
- Public/private IPv4 and IPv6 validation, mixed or invalid DNS answers,
  redirects, timeouts, conditional requests, and download-size boundaries.
- RSS/Atom parsing, missing metadata, duplicate entries, and repeat refreshes.
- SQLite uniqueness, concurrent inserts, cascading deletion, and transaction rollback.
- Web actions, CSRF, search, pagination, escaped content, safe failure messages,
  and database readiness.

To run one area while developing, for example:

```bash
python -m unittest discover -s tests -p 'test_feed_service.py' -v
```

## Continuous integration

The GitHub Actions workflow in `.github/workflows/tests.yml` runs on every push
and pull request. It uses Python 3.12 on Ubuntu, installs `requirements.txt`, and
runs the same `unittest` command shown above. Pip downloads are cached to speed
up later runs, and the job has a ten-minute timeout.

Results appear in the repository's **Actions** tab and in pull request checks.
The tests need no repository secrets, `.env` file, or pre-existing database.
The workflow starts running after this file is committed and pushed to GitHub.

## Fetching, parsing, and refresh behavior

Flask routes use `rss_reader/feed_service.py` for fetching and parsing feeds. Parsing receives downloaded bytes and returns
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
limits, timeouts, size limits, conditional requests, and web interface integration.
They make no live network requests.

## Forms, pages, and readiness

All state-changing browser forms require a random CSRF token bound to Flask's
signed session cookie. Tokens are checked on the server; missing, incorrect, or
other-session tokens return HTTP 400 before the action runs. Protection remains
enabled in tests. Session cookies use SameSite=Lax, and HTML responses use
`Cache-Control: no-store` so shared caches do not retain forms with session tokens.
The approach follows [OWASP's CSRF prevention guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Article pages fetch five rows at a time with SQLite `LIMIT`/`OFFSET`, ordered by
publication date and then article ID, both descending. Invalid page numbers
return 400; pages beyond the available results and missing feed IDs return 404.
An empty feed still has a valid first page with an explanatory message.

Templates share one base layout and one flash-message partial. Deletion opens a
confirmation page before the protected POST; viewing the confirmation does not
remove data. Submit buttons show progress and prevent repeat clicks while a
request is pending, and are restored when navigating back. Forms still work
without JavaScript. Edit validation and save failures retain entered values,
and optional subtitle/generator fields can be left blank.

`GET /healthz` returns `{"status":"ok"}` with HTTP 200 when the configured
on-disk database can be read and has the expected schema version and required
columns. It returns `{"status":"unavailable"}` with HTTP 503 otherwise. The
check opens SQLite read-only and never initializes a missing database. It checks
readiness, not remote feed availability, database write access, or full integrity.
It is intended for the application's on-disk SQLite setup, not `:memory:` databases.
