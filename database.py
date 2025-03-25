import sqlite3

def setup_database():
    
    conn = sqlite3.connect("rss_feeds.db")
    cursor = conn.cursor()

    # create feeds
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feeds(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   title TEXT,
                   link TEXT,
                   subtitle TEXT,
                   generator TEXT
                   )
    ''')

    # create articles
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS articles(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   feed_id INTEGER,
                   title TEXT,
                   link TEXT,
                   published TEXT,
                   author TEXT,
                   summary TEXT,
                   FOREIGN KEY(feed_id) REFERENCES feed(id)
                   )
    ''')

    conn.commit()
    conn.close()

def insert_feed(title, link, subtitle, generator):
    conn = sqlite3.connect("rss_feeds.db")
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR IGNORE INTO feeds(title, link, subtitle,generator)
        VALUES(?, ?, ?, ?)
    ''', (title, link, subtitle, generator))

    conn.commit()
    cursor.execute('''SELECT id FROM feeds WHERE link = ?''', (link,))
    feed = cursor.fetchone()
    conn.close()
    return feed[0] if feed else None 
    if feed_id is None:
        print("Error: Feed ID is None. Cannot insert article.")
        return

    # # Convert values to strings to avoid type issues
    # title = str(title) if title else "No title"
    # link = str(link) if link else "No link"
    # published = str(published) if published else "Unknown date"
    # author = str(author) if author else "Unknown author"
    # summary = str(summary) if summary else "No summary available"

    # conn = sqlite3.connect("rss_feeds.db")
    # cursor = conn.cursor()
    
    # try:
    #     cursor.execute('''
    #         INSERT OR IGNORE INTO articles (feed_id, title, link, published, author, summary)
    #         VALUES (?, ?, ?, ?, ?, ?)
    #     ''', (feed_id, title, link, published, author, summary))
    #     conn.commit()
    # except sqlite3.Error as e:
    #     print(f"SQLite error: {e}")
    # finally:
    #     conn.close()

def get_feed_id(link):
    conn = sqlite3.connect("rss_feeds.db")
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id FROM feeds WHERE link = ?
    ''', (link,))
    feed = cursor.fetchone()
    conn.close()
    return feed[0] if feed else None

def insert_article(feed_id, title, link, published, author, summary):
    conn = sqlite3.connect("rss_feeds.db")
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO articles (feed_id, title, link, published, author, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (feed_id, title, link, published, author, summary))

    conn.commit()
    conn.close()

# def get_articles(feed_id):
#     conn = sqlite3.connect("rss_feeds.db")
#     cursor = conn.cursor()

#     cursor.execute('''
#         SELECT title, link, published, author, summary FROM articles WHERE feed_id = ?
#     ''', (feed_id))

#     articles = cursor.fetchall()
#     conn.close()

#     return [{"title": row[0], "link": row[1], "published": row[2], "author": row[3], "summary": row[4]} for row in articles]

def get_articles(feed_id):
    if feed_id is None:
        print("Error: feed_id is None. Cannot retrieve articles.")
        return []

    conn = sqlite3.connect("rss_feeds.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT title, link, published, author, summary FROM articles WHERE feed_id = ?
        ''', (feed_id,))  # Ensure feed_id is in a tuple format
        
        articles = cursor.fetchall()
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        articles = []
    
    finally:
        conn.close()

    return [{"title": row[0], "link": row[1], "published": row[2], "author": row[3], "summary": row[4]} for row in articles]

def list_feeds():
    try:
        conn = sqlite3.connect("rss_feeds.db")
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, title, link FROM feeds 
        ''', )
        feeds = cursor.fetchall()
        return [{"id": row[0], "title": row[1], "link": row[2]} for row in feeds]

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    
    finally:
        conn.close()


def delete_feed(feed_id):
    try:

         # Debugging print
        print(f"Received feed_id = {feed_id}")

        conn = sqlite3.connect("rss_feeds.db")
        cursor = conn.cursor()

        # Check if the feed_id exists before deleting
        cursor.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,))
        if cursor.fetchone() is None:
            print(f"Error: Feed ID {feed_id} does not exist.")
            conn.close()
            return

        print(f"Deleting articles for feed_id = {feed_id}")
        cursor.execute('''DELETE FROM articles WHERE feed_id = ?''', (feed_id,))

        print(f" Deleting feed with ID = {feed_id}")
        cursor.execute('''DELETE FROM feeds WHERE id = ?''', (feed_id,))
        
        conn.commit()
        print(f"feed with id: {feed_id} has been deleted")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

    finally:
        conn.close()

def prompt_delete_feed():
    feeds = list_feeds()
    if not feeds:
        print("No feeds available")
        return
    
    print("Available feeds:")
    for feed in feeds:
        print(f"{feed['id']}: {feed['title']} {feed['link']}")

    try:
        feed_id_input = input("Enter the id of the feed you want to delete").strip()
        if not feed_id_input.isdigit():
            print("Error: Please enter a valid numerical ID.")
            return

        feed_id = int(feed_id_input)
        delete_feed(feed_id)
    except ValueError:
        print("Invalid input")


# def insert_feed(title, link, subtitle, generator):
#     conn = sqlite3.connect("rss_feeds.db")
#     cursor = conn.cursor()

#     conn.commit()
#     conn.close()
# run db setup
setup_database()
