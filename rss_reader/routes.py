import sqlite3

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from .database import (count_articles, database_ready, delete_feed, get_article_page,
                       get_feed_by_id, get_feed_id, save_feed, list_feeds, update_metadata)
from .errors import FeedFetchError, UnsafeFeedURLError
from .feed_service import fetch_feed
from .url_safety import normalize_url

web = Blueprint("web", __name__)


def require_feed(feed_id):
    feed = get_feed_by_id(feed_id)
    if feed is None:
        abort(404)
    return feed


@web.app_errorhandler(HTTPException)
def http_error(error):
    # Only our own explicit 400 descriptions contain user-facing guidance.
    message = error.description if error.code == 400 else {
        404: "The feed or page you requested could not be found.",
        405: "This action is not available using that request method.",
    }.get(error.code, "Unable to complete this request.")
    response = error.get_response()
    response.set_data(render_template("error.html", status=error.code, message=message))
    response.content_type = "text/html; charset=utf-8"
    return response


@web.app_errorhandler(sqlite3.Error)
def database_error(error):
    current_app.logger.error("Database request failed: endpoint=%s category=%s", request.endpoint, type(error).__name__)
    return render_template("error.html", status=503,
                           message="The reader is temporarily unavailable. Please try again later."), 503


@web.route("/healthz")
def health():
    try:
        ready = database_ready()
    except (sqlite3.Error, OSError, ValueError):
        ready = False
    if not ready:
        current_app.logger.warning("Readiness check failed: database unavailable")
    response = jsonify(status="ok" if ready else "unavailable")
    response.status_code = 200 if ready else 503
    response.headers["Cache-Control"] = "no-store"
    return response


@web.route("/")
def home():
    query = request.args.get("query", "").strip().lower()
    feeds = list_feeds()
    if query:
        feeds = [feed for feed in feeds if query in feed["title"].lower()
                 or query in (feed.get("subtitle") or "").lower()]
    return render_template("index.html", feeds=feeds, query=query)


@web.route("/add_feed", methods=["POST"])
def add_feed():
    try:
        source_url = normalize_url(request.form.get("feed_url", "").strip())
        if get_feed_id(source_url) is not None:
            flash("This feed is already added.", "warning")
        else:
            result = fetch_feed(source_url)
            _, created = save_feed(result)
            flash("Feed added successfully." if created else "This feed is already added.",
                  "success" if created else "warning")
    except FeedFetchError as error:
        current_app.logger.warning("Feed add failed: category=%s reason=%s", type(error).__name__, str(error))
        flash(str(error), "danger")
        return render_template("index.html", feeds=list_feeds(), query="",
                               feed_url="" if isinstance(error, UnsafeFeedURLError) else request.form.get("feed_url", "")), 400
    except sqlite3.Error as error:
        current_app.logger.error("Feed add failed: category=%s", type(error).__name__)
        flash("Unable to save the feed. Please try again.", "danger")
        return render_template("index.html", feeds=list_feeds(), query="",
                               feed_url=request.form.get("feed_url", "")), 503
    return redirect(url_for("web.home"))


@web.route("/feed/<int:feed_id>")
def view_feed(feed_id):
    feed = require_feed(feed_id)
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(400, description="Page must be a positive whole number.")
    if page < 1:
        abort(400, description="Page must be a positive whole number.")
    per_page = 5
    total_articles = count_articles(feed_id)
    total_pages = max(1, (total_articles + per_page - 1) // per_page)
    if page > total_pages:
        abort(404)
    articles = get_article_page(feed_id, page, per_page)
    return render_template("articles.html", feed=feed, articles=articles,
                           page=page, total_pages=total_pages, total_articles=total_articles)


@web.route("/delete_rss_feed/<int:feed_id>", methods=["GET", "POST"])
def delete_rss_feed(feed_id):
    feed = require_feed(feed_id)
    if request.method == "GET":
        return render_template("delete_feed.html", feed=feed)
    try:
        if not delete_feed(feed_id):
            abort(404)
        flash("Feed deleted successfully.", "success")
    except sqlite3.Error as error:
        current_app.logger.error("Feed delete failed: feed_id=%s category=%s", feed_id, type(error).__name__)
        flash("Unable to delete the feed. Please try again.", "danger")
        return render_template("delete_feed.html", feed=feed), 503
    return redirect(url_for("web.home"))


@web.route("/refresh_feed/<int:feed_id>", methods=["POST"])
def refresh_feed(feed_id):
    feed = require_feed(feed_id)
    try:
        result = fetch_feed(feed["source_url"], cached=feed)
        save_feed(result, feed_id=feed_id)
        flash("Feed is already up to date." if result.not_modified else "Feed refreshed successfully.", "success")
    except FeedFetchError as error:
        current_app.logger.warning("Feed refresh failed: feed_id=%s category=%s reason=%s", feed_id, type(error).__name__, str(error))
        flash(str(error), "danger")
    except (sqlite3.Error, ValueError) as error:
        current_app.logger.error("Feed refresh persistence failed: feed_id=%s category=%s", feed_id, type(error).__name__)
        flash("Unable to save the refresh. Existing articles were preserved.", "danger")
    return redirect(url_for("web.home"))


@web.route("/edit_feed/<int:feed_id>", methods=["GET", "POST"])
def edit_feed(feed_id):
    feed = require_feed(feed_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subtitle = request.form.get("subtitle", "").strip()
        generator = request.form.get("generator", "").strip()
        submitted = dict(feed, title=title, subtitle=subtitle, generator=generator)
        if not title:
            flash("Title cannot be empty.", "danger")
            return render_template("edit_feed.html", feed=submitted, title_error=True), 400
        try:
            if not update_metadata(feed_id, title, subtitle, generator):
                abort(404)
        except sqlite3.Error as error:
            current_app.logger.error("Feed edit failed: feed_id=%s category=%s", feed_id, type(error).__name__)
            flash("Unable to save your changes. Please try again.", "danger")
            return render_template("edit_feed.html", feed=submitted), 503
        flash("Feed metadata updated successfully.", "success")
        return redirect(url_for("web.home"))
    return render_template("edit_feed.html", feed=feed)
