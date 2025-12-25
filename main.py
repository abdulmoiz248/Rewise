import os
import requests
import random
from dotenv import load_dotenv
from datetime import datetime

from google import genai
from google.genai import types

from helpers import (
    get_database_pages,
    get_page_content,
    extract_text,
    append_to_rewise
)

load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# ───────────────────────────────────────────
# Gemini AI setup
# ───────────────────────────────────────────
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

model_id = "gemini-2.5-flash"

PROMPT = """You are an expert quiz maker. Generate 5-10 MCQs with 4 options (A-D), correct answer, and short explanation. Avoid repeating questions.

Given the following text, generate MCQs:

Text:
{input_text}

Output format:
Q1: Question?
A) ...
B) ...
C) ...
D) ...
Answer: <LETTER>
Explanation: <short>
"""

# ───────────────────────────────────────────
# Helper to find or create Rewise page
# ───────────────────────────────────────────
def get_or_create_rewise_page():
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    res = requests.post(url, headers=HEADERS).json()
    pages = res.get("results", [])
    
    for p in pages:
        title_prop = p["properties"].get("Name") or p["properties"].get("Title")
        title = ""
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
        if title.lower() == "rewise":
            return p["id"]
    
    # create page if not exists
    create_url = "https://api.notion.com/v1/pages"
    body = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": "Rewise"}}]}
        }
    }
    new_page = requests.post(create_url, headers=HEADERS, json=body).json()
    return new_page["id"]

REWISE_PAGE_ID = get_or_create_rewise_page()

# ───────────────────────────────────────────
# Pick one random page from database
# ───────────────────────────────────────────
pages = get_database_pages()
if not pages:
    raise Exception("No pages found in database!")

random_page = random.choice(pages)
pid = random_page["id"]

title_prop = random_page["properties"].get("Name") or random_page["properties"].get("Title")
page_title = (
    title_prop["title"][0]["plain_text"]
    if title_prop and title_prop.get("title")
    else "Untitled"
)

blocks = get_page_content(pid)
page_text = " ".join(extract_text(b) for b in blocks)

if not page_text.strip():
    raise Exception("Selected page has no content!")

# ───────────────────────────────────────────
# Generate MCQs
# ───────────────────────────────────────────
prompt = PROMPT.format(input_text=page_text)
response = client.models.generate_content(
    model=model_id,
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0.7)
)
quiz_output = response.text

# ───────────────────────────────────────────
# Send to Discord
# ───────────────────────────────────────────
discord_payload = {
    "content": f"📚 **Rewise MCQs ({datetime.now().strftime('%Y-%m-%d')}) - {page_title}**\n\n{quiz_output}"
}
requests.post(DISCORD_WEBHOOK, json=discord_payload)

# ───────────────────────────────────────────
# Append to Notion Rewise page
# ───────────────────────────────────────────
append_to_rewise(
    f"📚 **Rewise MCQs ({datetime.now().strftime('%Y-%m-%d')}) - {page_title}**\n{quiz_output}",
    REWISE_PAGE_ID
)

print(f"✅ MCQs generated from '{page_title}' and sent to Discord + Notion")
