import os

DIRECTORY_PATH = "../portfolio-website-nextjs/posts/"

def extract_files_from_directory():
    return os.listdir(DIRECTORY_PATH)


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
