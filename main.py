"""Optional terminal interface using the same service as the Flask routes."""
import sqlite3

from rss_reader import create_app
from rss_reader.database import delete_feed, get_articles, get_feed_id, list_feeds, save_feed
from rss_reader.errors import FeedFetchError
from rss_reader.feed_service import fetch_feed
from rss_reader.url_safety import normalize_url


def main_menu():
    while True:
        print("\nRSS Reader: 1 Add | 2 List | 3 View articles | 4 Delete | 5 Exit")
        choice = input("Choose an option: ").strip()
        try:
            if choice == "1":
                url = normalize_url(input("Feed URL: ").strip())
                if get_feed_id(url) is not None:
                    print("This feed is already added.")
                    continue
                _, created = save_feed(fetch_feed(url))
                print("Feed added." if created else "This feed is already added.")
            elif choice == "2":
                for feed in list_feeds():
                    print(f"{feed['id']}: {feed['title']} ({feed['source_url']})")
            elif choice == "3":
                for article in get_articles(int(input("Feed ID: "))):
                    print(f"{article['title']} ({article['url'] or 'No link'})")
                    print(article["summary"][:200])
            elif choice == "4":
                deleted = delete_feed(int(input("Feed ID: ")))
                print("Feed deleted." if deleted else "Feed not found.")
            elif choice == "5":
                break
            else:
                print("Choose a number from 1 to 5.")
        except FeedFetchError as error:
            print(str(error))
        except ValueError:
            print("Enter a valid numerical feed ID.")
        except sqlite3.Error:
            print("Database operation failed. Run init-db before using the reader.")


if __name__ == "__main__":
    with create_app().app_context():
        main_menu()
