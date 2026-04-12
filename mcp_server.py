import asyncio
import os
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from constants import BLOG_CONTENT_CATEGORY_ID, YOUTUBE_CONTENT_CATEGORY_ID

load_dotenv()
open_ai_api_key_secret = os.environ.get("open_ai_api_key_secret")

openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=open_ai_api_key_secret,
    model_name="text-embedding-3-small",
)

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
chromadb_client = chromadb.PersistentClient(path=db_path)
content_collection = chromadb_client.get_or_create_collection(
    name="content", embedding_function=openai_ef
)

CATEGORY_MAP = {
    "youtube": YOUTUBE_CONTENT_CATEGORY_ID,
    "blog": BLOG_CONTENT_CATEGORY_ID,
}

app = Server("content-search")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_content",
            description="Search across YouTube videos and blog posts using semantic search. Returns concise results with title, URL, type, and relevance score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant content",
                    },
                    "content_type": {
                        "type": "string",
                        "enum": ["youtube", "blog", "all"],
                        "description": "Filter by content type (default: all)",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 20)",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_content_detail",
            description="Get the full content and metadata for a specific content item by its ID. Use this after search_content to retrieve the full text of a blog post or YouTube video description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content_id": {
                        "type": "string",
                        "description": "The ID of the content item (returned by search_content)",
                    },
                },
                "required": ["content_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any):
    try:
        if name == "search_content":
            return handle_search(arguments)
        elif name == "get_content_detail":
            return handle_get_detail(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def handle_search(arguments: dict):
    query = arguments["query"]
    content_type = arguments.get("content_type", "all")
    num_results = min(arguments.get("num_results", 5), 20)

    where_filter = None
    if content_type in CATEGORY_MAP:
        where_filter = {"content_category_id": CATEGORY_MAP[content_type]}

    query_params = {
        "query_texts": [query],
        "n_results": num_results,
    }
    if where_filter:
        query_params["where"] = where_filter

    results = content_collection.query(**query_params)

    ids = results["ids"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    if not ids:
        return [TextContent(type="text", text="No results found.")]

    result = f"Found {len(ids)} results for: \"{query}\"\n\n"
    for i, (content_id, metadata, distance) in enumerate(zip(ids, metadatas, distances), 1):
        content_type_label = "YouTube" if metadata.get("content_category_id") == YOUTUBE_CONTENT_CATEGORY_ID else "Blog"
        result += f"{i}. [{content_type_label}] {metadata['title']}\n"
        result += f"   URL: {metadata['url']}\n"
        result += f"   ID: {content_id}\n"
        result += f"   Score: {distance:.4f}\n\n"

    return [TextContent(type="text", text=result)]


def handle_get_detail(arguments: dict):
    content_id = arguments["content_id"]

    results = content_collection.get(
        ids=[content_id],
        include=["documents", "metadatas"],
    )

    if not results["ids"]:
        return [TextContent(type="text", text=f"No content found with ID: {content_id}")]

    document = results["documents"][0]
    metadata = results["metadatas"][0]

    content_type_label = "YouTube" if metadata.get("content_category_id") == YOUTUBE_CONTENT_CATEGORY_ID else "Blog"

    result = f"Title: {metadata['title']}\n"
    result += f"Type: {content_type_label}\n"
    result += f"URL: {metadata['url']}\n"
    if metadata.get("thumbnail"):
        result += f"Thumbnail: {metadata['thumbnail']}\n"
    result += f"\n--- Content ---\n{document}\n"

    return [TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
