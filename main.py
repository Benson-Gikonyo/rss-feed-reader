import feedparser
import requests
import json
import os

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

    if 'title' not in resource.feed:
        print("Error: Invalid RSS feed or unable to retrieve data.")
        return None

    title = resource.feed.get('title', 'No title available')
    link = resource.feed.get('link', 'No link available')
    subtitle = resource.feed.get('subtitle', 'No subtitle available')
    generator = resource.feed.get('generator', 'No generator available')
    entries = resource.entries if 'entries' in resource else []
    
    feed_data = {
        "title": title,
        "link": link,
        "subtitle": subtitle,
        "generator": generator,
        "articles": [
            {
                "title": entry.get('title', 'No title'),
                "link": entry.get('link', 'No link'),
                "published": entry.get('published', 'No date'),
                "author" : entry.get('author', 'unknown author'),
                # summary = entry.get('content', 'No summary available')
                "summary" : get_content(entry)
            }
            for entry in entries[:5]
        ]
    }
    save_to_json(feed_data)
    return feed_data

def get_content(entry):
    '''safely extract content from rss feed'''
    if 'content' in entry and entry['content']:
        return entry['content'][0].get('value', 'no summary available')
    return entry.get('summary', 'No summary available')


def save_to_json(feed_data):
    '''Automatically save feed data to json file'''
    file_path = "savedfeeds.json"

    feeds = []
#  check for and load any existing data
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            try:
                feeds = json.load(file)
            except json.JSONDecodeError:
                feeds = []
            
    else:
        feeds = []

    feeds.append(feed_data)
# write new data to the file    
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(feeds, file, indent=4)
    print(f"\n✅ RSS feed saved to {file_path}\n")

# main execution
url = get_url()
parsed_data = None

if validate_url(url):
    parsed_data = parse_url(url)

if parsed_data:
    title, link, subtitle, generator, entries = parsed_data
    print(f"Title: {title}")
    print(f"Link: {link}")
    print(f"Subtitle: {subtitle}")
    print(f"Generator: {generator}")

    print("\n === Latest articles ===")
        # Show first 5 entries

        # for i, entry in enumerate(entries[:5], start=1): 
        #     article_title = entry.get('title', 'No title')
        #     article_link = entry.get('link', 'No link')
        #     published = entry.get('published', 'No date')
        #     author = entry.get('author', 'unknown author')
        #     # summary = entry.get('content', 'No summary available')
        #     summary = get_content(entry)
    for i, article in enumerate(parsed_data['articles'], start=1):
        print(f"\n{i}. {article['title']} ({article['link']})")
        print(f"   Published: {article['published']} | Author: {article['author']}")
        print(f"   Summary: {article['summary'][:200]}...")
           
        
else:
    print("No articles found on this feed")