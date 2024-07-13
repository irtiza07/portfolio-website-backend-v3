import os
import requests
import re

import psycopg2  # type: ignore
from dotenv import load_dotenv
from feedgen.feed import FeedGenerator, FeedEntry
from datetime import datetime, date
import pytz
from functools import lru_cache
from pydub import AudioSegment


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
OPENAI_SPEECH_API_ROUTE = "https://api.openai.com/v1/audio/speech"


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


def clean_mdx_content(mdx_content):
    # Remove metadata at the top
    mdx_content = re.sub(r"---\n.*?\n---\n", "", mdx_content, flags=re.DOTALL)

    # Remove URL references and keep the text
    mdx_content = re.sub(r"\[(.*?)\]\(https?://[^\)]+\)", r"\1", mdx_content)

    # Remove code blocks
    mdx_content = re.sub(r"```.*?```", "", mdx_content, flags=re.DOTALL)

    return mdx_content


@lru_cache(maxsize=200)
def generate_and_download_audio(input_text: str, output_file_name: str):
    segments = []
    max_chars_per_segment = 4096

    for start in range(0, len(input_text), max_chars_per_segment):
        segment = input_text[start : start + max_chars_per_segment]
        segments.append(segment)

    audio_file_names = []
    for index, segment in enumerate(segments):
        print(f"Processing file {output_file_name}, SEGMENT #{index}")
        headers = {
            "Authorization": f"Bearer {open_ai_api_key_secret}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "tts-1-hd",
            "input": segment,
            "voice": "shimmer",
        }

        audio_file_name = f"./audio/{output_file_name}-intermediate-{index}.mp3"
        audio_file_names.append(audio_file_name)

        response = requests.post(OPENAI_SPEECH_API_ROUTE, headers=headers, json=payload)
        if response.status_code == 200:
            with open(audio_file_name, "wb") as f:
                f.write(response.content)
            print(f"Audio file saved.")
        else:
            print(f"Request failed with status code {response.status_code}")

    print("Combining intermediate files...")
    combined_audio = sum(
        [AudioSegment.from_mp3(file_path) for file_path in audio_file_names]
    )
    combined_audio.export(f"./audio/{output_file_name}.mp3", format="mp3")
    print("Successfully created combined file.")

    print("Removing intermediate files...")
    for intermediate_file in audio_file_names:
        os.remove(intermediate_file)

    return combined_audio


for file_name in extract_files_from_directory(DIRECTORY_PATH):
    with open(generate_file_path(file_name), "r", encoding="utf-8") as file:
        md_content = clean_mdx_content(file.read())
        generate_and_download_audio(input_text=md_content, output_file_name=file_name)
