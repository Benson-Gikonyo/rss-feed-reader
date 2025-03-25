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

def parse_url(url):
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
    
    # check if feed exists, or insert it
    feed_id = get_feed_id(link)
    if not feed_id:
        feed_id = insert_feed(title, link, subtitle, generator)

    # store articles in the db
    for entry in entries[:5]:
        title = entry.get('title', 'No title')
        link = entry.get('link', 'No link')
        published = entry.get('published', 'No date')
        author = entry.get('author', 'unknown author')
        summary = get_content(entry)

        insert_article(feed_id, title, link, published, author, summary)

    print(f"Feed '{title}' successfully added.")
    # articles = get_articles(feed_id)
    # return title, link, subtitle, generator, articles
    return feed_id

def get_content(entry):
    '''safely extract content from rss feed'''
    if 'content' in entry and entry['content']:
        return entry['content'][0].get('value', 'no summary available')
    return entry.get('summary', 'No summary available')


# def save_to_json(feed_data):
#     '''Automatically save feed data to json file'''
#     file_path = "savedfeeds.json"

#     feeds = []
# #  check for and load any existing data
#     if os.path.exists(file_path):
#         with open(file_path, "r", encoding="utf-8") as file:
#             try:
#                 feeds = json.load(file)
#             except json.JSONDecodeError:
#                 feeds = []
            
#     else:
#         feeds = []

#     feeds.append(feed_data)
# # write new data to the file    
#     with open(file_path, "w", encoding="utf-8") as file:
#         json.dump(feeds, file, indent=4)
#     print(f"\n✅ RSS feed saved to {file_path}\n")

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


# # main execution

# url = get_url()
# parsed_data = None

# if validate_url(url):
#     parsed_data = parse_url(url)

# if parsed_data:
#     title, link, subtitle, generator, articles = parsed_data
#     print(f"Title: {title}")
#     print(f"Link: {link}")
#     print(f"Subtitle: {subtitle}")
#     print(f"Generator: {generator}")

#     print("\n === Latest articles ===")
        
#     for i, article in enumerate(articles, start=1):
#         print(f"\n{i}. {article['title']} ({article['link']})")
#         print(f"   Published: {article['published']} | Author: {article['author']}")
#         print(f"   Summary: {article['summary'][:200]}...")
           
        
# else:
#     print("No articles found on this feed")