from flask import Flask, render_template, request, url_for, flash, redirect
import feedparser
from database import list_feeds, get_articles, get_feed_id, insert_feed, delete_feed, get_feed_by_id, insert_article, delete_articles_by_feed,  update_metadata
from main import parse_url
from dotenv import load_dotenv
import os

load_dotenv()


app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

# list feeds
@app.route('/')
def home():
    # feeds = list_feeds()
    # return render_template('index.html', feeds=feeds)

    query = request.args.get("query", "").strip().lower()
    feeds = list_feeds()

    if query:
        feeds = [feed for feed in feeds if query in feed["title"].lower() or query in feed.get("subtitle", "").lower()]

    return render_template("index.html", feeds=feeds)

# add feed
@app.route("/add_feed", methods=["POST"])
def add_feed():
    feed_url = request.form.get("feed_url").strip()

    if not feed_url.startswith(("http://", "https://")):
        flash("Invalid url. Please enter a valid rss feed link")
        return redirect(url_for("home"))

    if get_feed_id(feed_url):
        flash("This feed is already added.")
        return redirect(url_for("home"))
    
    parsed_data = parse_url(feed_url)

    if not parsed_data:
        flash("invalid rss feed or unable to retrieve data ")
        return redirect(url_for("home"))
    
    title, link, subtitle, generator, _ = parsed_data

    print(f"DEBUG: Parsed feed link -> {link}")  # 🔍 Check if the extracted link is correct

    existing_feed_id = get_feed_id(link)  # ✅ Check if the feed already exists

    print(f"DEBUG: Existing feed_id for link '{link}' -> {existing_feed_id}")  # 🔍 Check what get_feed_id() returns

    if existing_feed_id:
        flash("This feed is already added.", "warning")
    else:
        insert_feed(title, link, subtitle, generator)
        flash("Feed added successfully", "success")

    return redirect(url_for("home"))

    flash("Feed added successfully ")
    return redirect(url_for("home"))


# view feed(articles)
@app.route("/feed/<int:feed_id>")
def view_feed(feed_id):
    page = request.args.get("page", 1, type=int)
    per_page = 5
    offset = (page - 1) * per_page

    feed = get_feed_by_id(feed_id)
    if not feed:
        flash("Feed not found", "danger")
        return redirect(url_for("home"))

    all_articles = get_articles(feed_id)
    total_articles = len(all_articles)
    articles = all_articles[offset:offset + per_page]

    total_pages = (total_articles + per_page - 1) // per_page

    return render_template("articles.html", feed=feed, articles=articles, page=page, total_pages=total_pages)

# delete feed
@app.route("/delete_rss_feed/<int:feed_id>", methods=["POST"])
def delete_rss_feed(feed_id):
    try:
        delete_feed(feed_id)

        flash("Feed deleted successfully", "success")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Error deleting feed: {e}", "danger")
        return redirect(url_for("home"))
    
# refresh feed
@app.route("/refresh_feed/<int:feed_id>", methods=["POST"])
def refresh_feed(feed_id):
    feed = get_feed_by_id(feed_id)

    if not feed:
        flash("Feed not found.", "danger")
        return redirect(url_for("home"))
    
    url = feed['link']
    _, _, _, _, articles = parse_url(url, is_refresh=True)

    if not articles:
        flash("No new articles found, Failed to refresh feed", "Warning")
        return redirect(url_for("home"))
    
    # remove old articles and store new ones
    delete_articles_by_feed(feed_id) 

    for article in articles:
        title = article["title"]
        link = article["link"]
        published = article["published"]
        author = article["author"]
        summary = article["summary"]

        # insert_article(
        #     feed_id,
        #     article["title"],
        #     article["link"],
        #     article["published"],
        #     article["author"],
        #     article["summary"],
        # )
        # title, link, published, author, summary = article  # Unpacking tuple
        insert_article(feed_id, title, link, published, author, summary)

    flash("Feed refreshed successfully!", "Success")
    return redirect(url_for("home"))

# edit feed metadata
@app.route("/edit_feed/<int:feed_id>", methods=["GET", "POST"])
def edit_feed(feed_id):
    feed = get_feed_by_id(feed_id)

    if not feed:
        flash("Feed not found", "danger")
        return redirect(url_for("home"))
    
    if request.method == "POST":

        print(f"DEBUG: Received POST request for feed_id {feed_id}")

        # Print form data to check if 'title' exists
        print(f"DEBUG: Form Data: {request.form}")


        title = request.form.get("title", "").strip()
        subtitle = request.form.get("subtitle", "").strip()
        generator = request.form.get("generator", "").strip()

        if not title:  # Ensure title is provided
            flash("Title cannot be empty!", "danger")
            return redirect(url_for("edit_feed", feed_id=feed_id))

        update_metadata(feed_id, title, subtitle, generator)

        flash("Feed metadata updated successfully.", "success")
        return redirect(url_for("home"))

    return render_template("edit_feed.html", feed=feed)

if __name__ == '__main__':
    app.run(debug=True)