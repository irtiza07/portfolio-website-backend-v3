import requests
import os
import psycopg2  # type: ignore
from functools import lru_cache
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel

# Access environment variables
load_dotenv()
dbname_secret = os.environ.get("dbname_secret")
db_user_secret = os.environ.get("db_user_secret")
db_pass_secret = os.environ.get("db_pass_secret")
db_host_secret = os.environ.get("db_host_secret")
db_port_secret = os.environ.get("db_port_secret")
open_ai_api_key_secret = os.environ.get("open_ai_api_key_secret")
youtube_api_key = os.environ.get("youtube_api_key")

DIRECTORY_PATH = "../portfolio-website-nextjs/posts/"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class CreateEmbeddingsRequest(BaseModel):
    youtube: bool
    blog: bool
    force_refresh: bool = False


# Create an instance of the FastAPI class
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Mount the 'audio' directory to serve static files
app.mount("/audio", StaticFiles(directory="audio"), name="audio")


def close_db_conn(conn, cursor):
    cursor.close()
    conn.close()
    print("Cleaned up DB connections...")


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


def extract_files_from_directory(directory_path):
    return os.listdir(directory_path)


def generate_file_path(file_name):
    return os.path.join(DIRECTORY_PATH, file_name)


def parse_url_from_metadata(file_name):
    parsed_slug = file_name.split("/")[-1].split(".")[0]
    return f"https://irtizahafiz.com/blog/{parsed_slug}"


def parse_title_from_metadata(lines):
    for line in lines:
        if line.startswith("title:"):
            return line.split(":")[1].strip()


def parse_description_from_metadata(lines):
    for line in lines:
        if line.startswith("description:"):
            return line.split(":")[1].strip()


@lru_cache(maxsize=200)
def get_embeddings_from_openai(input_text: str):
    headers = {
        "Authorization": f"Bearer {open_ai_api_key_secret}",
        "Content-Type": "application/json",
    }
    payload = {"model": "text-embedding-3-small", "input": input_text}
    response = requests.post(OPENAI_EMBEDDINGS_URL, headers=headers, json=payload)

    return response.json()["data"][0]["embedding"]


def insert_blog_metadata_in_database(
    db_conn, cursor, title, url, embeddings, description
):
    query = "INSERT INTO content (title, url, category, blog_embedding, description) VALUES (%s, %s, 0, %s, %s);"
    cursor.execute(query, (title, url, embeddings, description))
    db_conn.commit()
    return


def insert_video_metadata_in_database(
    db_conn, cursor, title, url, thumbnail, embeddings
):
    query = "INSERT INTO content (title, url, category, thumbnail, blog_embedding) VALUES (%s, %s, 1, %s, %s);"
    cursor.execute(query, (title, url, thumbnail, embeddings))
    db_conn.commit()
    return


def get_top_recommendations(query_string):
    try:
        db_conn = get_db_conn()
        cursor = db_conn.cursor()
        query_string_embedding = get_embeddings_from_openai(query_string)

        query = """
            SELECT title, url, (1 - (blog_embedding <=> %s)) AS scores, category, thumbnail  FROM content ORDER BY scores DESC LIMIT 10;
        """
        cursor.execute(query, (str(query_string_embedding),))

        rows = cursor.fetchall()
        return [row for row in rows]

    finally:
        close_db_conn(db_conn, cursor)


def update_blog_metadata_db(force_refresh: bool = False):
    try:
        db_conn = get_db_conn()
        cursor = db_conn.cursor()

        cursor.execute("SELECT url FROM content")
        rows = cursor.fetchall()
        stored_blogs_urls = [row[0] for row in rows]

        for file_name in extract_files_from_directory(DIRECTORY_PATH):
            with open(generate_file_path(file_name), "r", encoding="utf-8") as file:
                md_content = file.read()
                url = parse_url_from_metadata(file.name)
                if (url in stored_blogs_urls) and not force_refresh:
                    print("Skipping. Blog exists in DB.")
                    continue
                else:
                    print("Processing. New blog found.")
                    file.seek(0)

                    lines = file.readlines()
                    title = parse_title_from_metadata(lines)
                    description = parse_description_from_metadata(lines)
                    embeddings = get_embeddings_from_openai(md_content)

                    insert_blog_metadata_in_database(
                        db_conn, cursor, title, url, embeddings, description
                    )
    finally:
        close_db_conn(db_conn, cursor)


def create_youtube_embeddings(force_refresh: bool = False):
    try:
        keep_parsing = True
        next_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId=UUDankIVMXJEkhtjv5yLSN4g&key={youtube_api_key}"

        db_conn = get_db_conn()
        cursor = db_conn.cursor()
        cursor.execute("SELECT url FROM content WHERE category=1;")
        stored_video_urls = [row[0] for row in cursor.fetchall()]

        while keep_parsing:
            response = requests.get(next_url).json()
            next_page_token = response.get("nextPageToken", None)
            if next_page_token:
                paginated_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId=UUDankIVMXJEkhtjv5yLSN4g&key={youtube_api_key}&pageToken={next_page_token}"
                next_url = paginated_url

            if not next_page_token:
                keep_parsing = False

            items = response["items"]
            for item in items:
                title = item["snippet"]["title"]
                description = item["snippet"]["description"]
                thumbnail = item["snippet"]["thumbnails"]["high"]["url"]
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                content_to_embed = f"Title: {title} \n Description: {description}"

                if (video_url in stored_video_urls) and not force_refresh:
                    print("Skipping. Video exists in DB.")
                    continue
                else:
                    print("Processing. New video found.")
                    embeddings = get_embeddings_from_openai(content_to_embed)
                    insert_video_metadata_in_database(
                        db_conn=db_conn,
                        cursor=cursor,
                        title=title,
                        url=video_url,
                        thumbnail=thumbnail,
                        embeddings=embeddings,
                    )

    finally:
        close_db_conn(db_conn, cursor)


@app.get("/recommendations")
def get_users_top_recommendations(
    user_query: str = Query(default="Programming", max_length=100)
):
    return {"data": get_top_recommendations(user_query)}


@app.post("/create_embeddings")
def create_embeddings(request: CreateEmbeddingsRequest):
    if request.youtube:
        create_youtube_embeddings(force_refresh=request.force_refresh)
    if request.blog:
        update_blog_metadata_db(force_refresh=request.force_refresh)

    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
