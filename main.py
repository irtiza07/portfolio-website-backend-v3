import requests
import os
import psycopg2  # type: ignore
from functools import lru_cache
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


# Access environment variables
load_dotenv()
dbname_secret = os.environ.get("dbname_secret")
db_user_secret = os.environ.get("db_user_secret")
db_pass_secret = os.environ.get("db_pass_secret")
db_host_secret = os.environ.get("db_host_secret")
db_port_secret = os.environ.get("db_port_secret")
open_ai_api_key_secret = os.environ.get("open_ai_api_key_secret")

DIRECTORY_PATH = "../posts"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

# Create an instance of the FastAPI class
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def close_db_conn(conn, cursor):
    cursor.close()
    conn.close()
    print("Cleaned up DB connections...")


def get_db_conn():
    # Connect to the PostgreSQL database
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


@lru_cache(maxsize=50)
def get_embeddings_from_openai(input_text: str):
    print("Cache miss. OpenAI API request being made.")
    headers = {
        "Authorization": f"Bearer {open_ai_api_key_secret}",
        "Content-Type": "application/json",
    }
    payload = {"model": "text-embedding-3-small", "input": input_text}
    response = requests.post(OPENAI_EMBEDDINGS_URL, headers=headers, json=payload)

    return response.json()["data"][0]["embedding"]


def insert_blog_metadata_in_database(db_conn, cursor, title, url, embeddings):
    query = "INSERT INTO content (title, url, category, blog_embedding) VALUES (%s, %s, 0, %s);"
    cursor.execute(query, (title, url, embeddings))
    db_conn.commit()
    return


def get_top_recommendations(query_string):
    try:
        db_conn = get_db_conn()
        cursor = db_conn.cursor()
        query_string_embedding = get_embeddings_from_openai(query_string)

        query = """
            SELECT title, url, (1 - (blog_embedding <=> %s)) AS scores  FROM content ORDER BY scores DESC LIMIT 3;
        """
        cursor.execute(query, (str(query_string_embedding),))

        rows = cursor.fetchall()
        return [row for row in rows]

    finally:
        close_db_conn(db_conn, cursor)


def update_blog_metadata_db():
    try:
        db_conn = get_db_conn()
        cursor = db_conn.cursor()
        force_write = False
        for file_name in extract_files_from_directory(DIRECTORY_PATH):
            print(f"Processing file: {file_name}")
            with open(generate_file_path(file_name), "r", encoding="utf-8") as file:
                md_content = file.read()
                url = parse_url_from_metadata(file.name)

                file.seek(0)

                lines = file.readlines()
                title = parse_title_from_metadata(lines)

                if force_write:
                    embeddings = get_embeddings_from_openai(md_content)
                    insert_blog_metadata_in_database(
                        db_conn, cursor, title, url, embeddings
                    )
    finally:
        close_db_conn(db_conn, cursor)


@app.get("/recommendations")
def get_users_top_recommendations(user_query: str = "Programming"):
    return {"data": get_top_recommendations(user_query)}


# Run the app with Uvicorn server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
