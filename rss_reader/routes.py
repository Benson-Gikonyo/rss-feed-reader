import sqlite3

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .database import (delete_feed, get_articles, get_feed_by_id, get_feed_id,
                       save_feed, list_feeds, update_metadata)
from .errors import FeedFetchError
from .feed_service import fetch_feed
from .url_safety import normalize_url


web = Blueprint("web", __name__)


@web.route("/")
def home():
    query = request.args.get("query", "").strip().lower()
    feeds = list_feeds()

    if query:
        feeds = [
            feed
            for feed in feeds
            if query in feed["title"].lower()
            or query in feed.get("subtitle", "").lower()
        ]

    return render_template("index.html", feeds=feeds)


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
    except sqlite3.Error:
        current_app.logger.error("Feed add failed: database error")
        flash("Unable to save the feed.", "danger")
    return redirect(url_for("web.home"))


@web.route("/feed/<int:feed_id>")
def view_feed(feed_id):
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 5
    offset = (page - 1) * per_page

    feed = get_feed_by_id(feed_id)
    if not feed:
        flash("Feed not found.", "danger")
        return redirect(url_for("web.home"))

    all_articles = get_articles(feed_id)
    total_articles = len(all_articles)
    articles = all_articles[offset : offset + per_page]
    total_pages = (total_articles + per_page - 1) // per_page

    return render_template(
        "articles.html",
        feed=feed,
        articles=articles,
        page=page,
        total_pages=total_pages,
    )


@web.route("/delete_rss_feed/<int:feed_id>", methods=["POST"])
def delete_rss_feed(feed_id):
    try:
        delete_feed(feed_id)
        flash("Feed deleted successfully.", "success")
    except Exception:
        flash("Unable to delete the feed.", "danger")

    return redirect(url_for("web.home"))


@web.route("/refresh_feed/<int:feed_id>", methods=["POST"])
def refresh_feed(feed_id):
    feed = get_feed_by_id(feed_id)

    if not feed:
        flash("Feed not found.", "danger")
        return redirect(url_for("web.home"))

    try:
        result = fetch_feed(feed["source_url"], cached=feed)
        save_feed(result, feed_id=feed_id)
        flash("Feed is already up to date." if result.not_modified else "Feed refreshed successfully.",
              "success")
    except FeedFetchError as error:
        current_app.logger.warning("Feed refresh failed: feed_id=%s category=%s reason=%s", feed_id, type(error).__name__, str(error))
        flash(str(error), "danger")
    except (sqlite3.Error, ValueError):
        current_app.logger.error("Feed refresh persistence failed: feed_id=%s", feed_id)
        flash("Unable to save the refresh. Existing articles were preserved.", "danger")
    return redirect(url_for("web.home"))


@web.route("/edit_feed/<int:feed_id>", methods=["GET", "POST"])
def edit_feed(feed_id):
    feed = get_feed_by_id(feed_id)

    if not feed:
        flash("Feed not found.", "danger")
        return redirect(url_for("web.home"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subtitle = request.form.get("subtitle", "").strip()
        generator = request.form.get("generator", "").strip()

        if not title:
            flash("Title cannot be empty.", "danger")
            return redirect(url_for("web.edit_feed", feed_id=feed_id))

        update_metadata(feed_id, title, subtitle, generator)
        flash("Feed metadata updated successfully.", "success")
        return redirect(url_for("web.home"))

    return render_template("edit_feed.html", feed=feed)
