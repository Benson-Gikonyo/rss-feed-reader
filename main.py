import feedparser
import requests
# import json
# import os
from database import insert_feed, get_feed_id, insert_article, get_articles, list_feeds, delete_feed, prompt_delete_feed

# get the url of the rss site to parse
def get_url():
    while True: 
        url = input("Enter the url for the site").strip()
        if url.startswith(("http://", "https://")):
            return url
        print("Error. Invalid url. Try again")

def validate_url(url):
    '''validate url'''
    # check if url is reachable before parsing
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True

        print(f"Error.Unable to access url(Status code: {response.status_code})")

    except requests.RequestException as e:
        print(f"Error. unable to reach url - {e}")
    
    return False

def parse_url(url, is_refresh=False):
    '''parse url feed'''
    resource = feedparser.parse(url)

    if not resource.feed:
        print(f"Error.Invalid rss feed or unable to retrieve data")
        return None

    title = resource.feed.get('title', 'No title available')
    link = resource.feed.get('link', 'No link available')
    subtitle = resource.feed.get('subtitle', 'No subtitle available')
    generator = resource.feed.get('generator', 'No generator available')
    entries = resource.entries if 'entries' in resource else []
    
    # Only insert feed if it's NOT a refresh
    if not is_refresh:
        feed_id = get_feed_id(link)
        if not feed_id:
            feed_id = insert_feed(title, link, subtitle, generator)
            print(f"Feed inserted with ID: {feed_id}")  # Debug statement
    else:
        feed_id = get_feed_id(link)  # Just get feed ID without inserting


    # store articles in the db
    for entry in entries[:5]:
        title = entry.get('title', 'No title')
        link = entry.get('link', 'No link')
        published = entry.get('published', 'No date')
        author = entry.get('author', 'unknown author')
        summary = get_content(entry)

        print(f"Inserting article: {title}, {link}")  # Debug statement
        insert_article(feed_id, title, link, published, author, summary)

    # print(f"Feed '{title}' successfully added.")
    articles = get_articles(feed_id)
    return title, link, subtitle, generator, articles

def get_content(entry):
    '''safely extract content from rss feed'''
    if 'content' in entry and entry['content']:
        return entry['content'][0].get('value', 'no summary available')
    return entry.get('summary', 'No summary available')

def view_articles():
    feeds = list_feeds()
    if not feeds:
        print("no feeds available")
        return

    print("\n Available Feeds")
    for feed in feeds:
        print(f"{feed['id']}: {feed['title']}, ({feed['link']})")

    try:
        feed_id = feed_id = int(input("Enter the id of the feed to view the feed").strip())
        articles = get_articles(feed_id)

        if not articles:
            print("No articles found for this feed")
            return
    
        print("\n === Latest articles ===")
        for i, article in enumerate(articles, start=1):
            print(f"\n{i}. {article['title']} ({article['link']})")
            print(f"   Published: {article['published']} | Author: {article['author']}")
            print(f"   Summary: {article['summary'][:200]}...")
        
    except ValueError:
        print("invalid input. Please enter a valid feed id")

def main_menu():
    '''rss reader menu'''
    while True:
        print("\n RSS Reader Menu")
        print("1 - Add a new RSS Feed")
        print("2 - List available Feed")
        print("3 - View articles from a Feed")
        print("4 - Delete a feed")
        print("5 - Exit")

        choice  = int(input("Choose an option: ").strip())

        if choice == 1:
            url = get_url()
            if validate_url(url):
                parse_url(url)
            
        elif choice == 2:
            feeds = list_feeds()
            if feeds:
                print("\n Saved feeds:")
                for feed in feeds:
                    print(f"{feed['id']}: {feed['title']} ({feed['link']})")
                else:
                    print("No feeds available")
        
        elif choice == 3:
            view_articles()
        
        elif choice == 4:
            prompt_delete_feed()

        elif choice == 5:
            print("Exiting RSS Reader...")
            break
        else:
            print("invalid option. please choose again")

if __name__ == "__main__":
    main_menu()
