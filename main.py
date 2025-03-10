import feedparser
import requests

# get the url of the rss site to parse
def get_url():
    while True: 
        url = input("Enter the url for the site").strip()
        if url.startswith(("http://", "https://")):
            return url
        print("Error. Invalid url. Try again")

def validate_url(url):
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
    

    return title, link, subtitle, generator, resource.entries

url = get_url()
parsed_data = parse_url(url)

if parsed_data:
    title, link, subtitle, generator, entries = parsed_data
    print(f"Title: {title}")
    print(f"Link: {link}")
    print(f"Subtitle: {subtitle}")
    print(f"Generator: {generator}")

    if entries:
        print("\n === Latest articles ===")
        # Show first 5 entries

        for i, entry in enumerate(entries[:5], start=1): 
            article_title = entry.get('title', 'No title')
            article_link = entry.get('link', 'No link')
            published = entry.get('published', 'No date')
            author = entry.get('author', 'unknown author')
            summary = entry.get('content', 'No summary available')

            print(f"\n{i}. {article_title} ({article_link})")
            print(f"   Published: {published} | Author: {author}")
            print(f"   Summary: {summary[:200]}...")
           
        
    else:
        print("No articles found on this feed")