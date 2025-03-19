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


# def insert_feed(title, link, subtitle, generator):
#     conn = sqlite3.connect("rss_feeds.db")
#     cursor = conn.cursor()

#     conn.commit()
#     conn.close()
# run db setup
setup_database()
