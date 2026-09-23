from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import (
    replace_articles,
    delete_feed,
    get_articles,
    get_feed_by_id,
    get_feed_id,
    save_feed,
    list_feeds,
    update_metadata,
)
from main import parse_url


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
    feed_url = request.form.get("feed_url", "").strip()

    if not feed_url.startswith(("http://", "https://")):
        flash("Invalid URL. Please enter a valid RSS feed link.", "danger")
        return redirect(url_for("web.home"))

    if get_feed_id(feed_url):
        flash("This feed is already added.", "warning")
        return redirect(url_for("web.home"))

    parsed_data = parse_url(feed_url)

    if not parsed_data:
        flash("Invalid RSS feed or unable to retrieve data.", "danger")
        return redirect(url_for("web.home"))

    title, link, subtitle, generator, articles = parsed_data
    existing_feed_id = get_feed_id(link)

    if existing_feed_id:
        flash("This feed is already added.", "warning")
    else:
        save_feed(title, link, subtitle, generator, articles)
        flash("Feed added successfully.", "success")

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

    parsed_data = parse_url(feed["link"], is_refresh=True)
    if not parsed_data:
        flash("Unable to refresh the feed.", "danger")
        return redirect(url_for("web.home"))

    _, _, _, _, articles = parsed_data
    if not articles:
        flash("No new articles found.", "warning")
        return redirect(url_for("web.home"))

    replace_articles(feed_id, articles)

    flash("Feed refreshed successfully.", "success")
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
