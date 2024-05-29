import os
import psycopg2  # type: ignore
from dotenv import load_dotenv
from feedgen.feed import FeedGenerator, FeedEntry
from datetime import datetime, date
import pytz


# Access environment variables
load_dotenv()
dbname_secret = os.environ.get("dbname_secret")
db_user_secret = os.environ.get("db_user_secret")
db_pass_secret = os.environ.get("db_pass_secret")
db_host_secret = os.environ.get("db_host_secret")
db_port_secret = os.environ.get("db_port_secret")

GENERATED_FEED_FILE_OUTPUT_DIRECTORY = "../portfolio-website-nextjs/public/"


def get_db_conn():
    try:
        conn = psycopg2.connect(
            dbname=dbname_secret,
            user=db_user_secret,
            password=db_pass_secret,
            host=db_host_secret,
            port=db_port_secret,
        )
        print("Connected to the database!")
        return conn

    except psycopg2.Error as e:
        print("Error: Unable to connect to the database.")
        print(e)


db_conn = get_db_conn()
cursor = db_conn.cursor()
cursor.execute(
    "SELECT title, url, created_at, id, description FROM content WHERE category=0 ORDER BY created_at ASC"
)
rows = cursor.fetchall()
print(rows)

# Create a FeedGenerator object
fg = FeedGenerator()

# Set up the basic feed information
fg.title("Irtiza Hafiz")
fg.link(href="https://irtizahafiz.com", rel="alternate")
fg.description("Random thoughts about programming, productivity, travel and life.")

# Add entries to the feed
# For each entry, provide at least title, link, and description
for row in rows:
    feed_entry_to_add = FeedEntry()

    feed_entry_to_add.title(row[0])
    publish_date = datetime.combine(row[2], datetime.min.time(), tzinfo=pytz.utc)
    feed_entry_to_add.updated(publish_date)
    feed_entry_to_add.author(
        {"name": "Irtiza Hafiz", "email": "irtizahafiz9@gmail.com"}
    )
    feed_entry_to_add.content(row[1])
    feed_entry_to_add.link({"href": row[1], "title": row[0]})
    feed_entry_to_add.description(row[4])
    feed_entry_to_add.guid(str(row[3]))
    feed_entry_to_add.pubDate(publish_date)

    fg.add_entry(feed_entry_to_add)


# Generate the XML feed
rss_feed = fg.rss_str(pretty=True).decode("utf-8")


# Write the XML feed to a file
feed_file_path = os.path.join(GENERATED_FEED_FILE_OUTPUT_DIRECTORY, "feed.xml")
with open(feed_file_path, "w", encoding="utf-8") as f:
    f.write(rss_feed)

print(f"feed.xml has been written to {feed_file_path}")
