import chromadb
from chromadb.utils import embedding_functions
import requests
import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel
from utils import (
    extract_files_from_directory,
    generate_file_path,
    parse_description_from_metadata,
    parse_title_from_metadata,
    parse_url_from_metadata,
)
from typing import List, Optional

# Access environment variables
load_dotenv()
open_ai_api_key_secret = os.environ.get("open_ai_api_key_secret")
youtube_api_key = os.environ.get("youtube_api_key")

DIRECTORY_PATH = "../portfolio-website-nextjs/posts/"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

YOUTUBE_CONTENT_CATEGORY_ID = 1
BLOG_CONTENT_CATEGORY_ID = 2

openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=open_ai_api_key_secret,
    model_name="text-embedding-3-small",
)

chromadb_client = chromadb.PersistentClient(path="./db")
content_collection = chromadb_client.get_or_create_collection(
    name="content", embedding_function=openai_ef
)


class CreateEmbeddingsRequest(BaseModel):
    youtube: bool
    blog: bool


class Recommendation(BaseModel):
    title: str
    url: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    content_category_id: int
    score: float


class RecommendationsResponse(BaseModel):
    data: List[Recommendation]


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def get_top_recommendations(query_string: str):
    results = content_collection.query(
        query_texts=[query_string],
        n_results=5,
    )

    # Extract the first (and only) list from results["documents"], results["metadatas"], and results["distances"]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    recommendations = []
    for i, (doc, metadata) in enumerate(zip(documents, metadatas)):
        recommendations.append(
            {
                "title": metadata["title"],
                "url": metadata["url"],
                "description": metadata.get("description", ""),
                "thumbnail": metadata.get("thumbnail", None),
                "content_category_id": metadata.get("content_category_id"),
                "score": distances[i],  # Use the corresponding distance
            }
        )

    return recommendations


def create_blog_embeddings():
    for file_name in extract_files_from_directory():
        with open(generate_file_path(file_name), "r", encoding="utf-8") as file:
            md_content = file.read()
            blog_url = parse_url_from_metadata(file.name)

            existing_items = content_collection.get(ids=[blog_url])

            if existing_items["ids"]:  # If the video_id exists, skip it
                print(f"Skipping video_id {blog_url}. Already exists in the database.")
                continue
            else:
                print("Processing. New blog found.")
                file.seek(0)

                lines = file.readlines()
                title = parse_title_from_metadata(lines)
                description = parse_description_from_metadata(lines)

                content_collection.add(
                    documents=[md_content],
                    metadatas=[
                        {
                            "title": title,
                            "url": blog_url,
                            "description": description,
                            "content_id": blog_url,
                            "content_category_id": BLOG_CONTENT_CATEGORY_ID,
                        }
                    ],
                    ids=[blog_url],
                )


def create_youtube_embeddings():
    keep_parsing = True
    next_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId=UUDankIVMXJEkhtjv5yLSN4g&key={youtube_api_key}"

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
            video_id = item["snippet"]["resourceId"]["videoId"]
            content_to_embed = f"Title: {title} \n Description: {description}"

            # Create a clean metadata dictionary from scratch
            existing_items = content_collection.get(ids=[video_id])

            if existing_items["ids"]:  # If the video_id exists, skip it
                print(f"Skipping video_id {video_id}. Already exists in the database.")
                continue
            else:
                print("New video found. Creating embedding and adding to DB.")
                content_collection.add(
                    documents=[content_to_embed],
                    metadatas=[
                        {
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                            "description": description,
                            "content_id": video_id,
                            "content_category_id": YOUTUBE_CONTENT_CATEGORY_ID,
                        }
                    ],
                    ids=[video_id],
                )


@app.get("/recommendations", response_model=RecommendationsResponse)
def get_users_top_recommendations(
    user_query: str = Query(default="Programming", max_length=100)
):
    return {"data": get_top_recommendations(user_query)}


@app.post("/create_embeddings")
def create_embeddings(request: CreateEmbeddingsRequest):
    if request.youtube:
        create_youtube_embeddings()
    if request.blog:
        create_blog_embeddings()

    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
