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
    get_or_create_tracking_page,
    select_page_for_review,
    clean_ai_response,
    parse_mcqs,
    append_to_rewise_formatted,
    update_page_tracking
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
TRACKING_PAGE_ID = get_or_create_tracking_page()

# ───────────────────────────────────────────
# Smart page selection (not random)
# ───────────────────────────────────────────
pages = get_database_pages()
if not pages:
    raise Exception("No pages found in database!")

selected_page = select_page_for_review(pages, TRACKING_PAGE_ID)
if not selected_page:
    raise Exception("No suitable page found for review!")

pid = selected_page["id"]

title_prop = selected_page["properties"].get("Name") or selected_page["properties"].get("Title")
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
raw_output = response.text

# Clean AI response (remove conversational text)
quiz_output = clean_ai_response(raw_output)

# Parse MCQs: questions only vs full with answers
questions_only, full_with_answers = parse_mcqs(quiz_output)

# Count MCQs
mcq_count = len([line for line in quiz_output.split("\n") if line.strip().startswith(("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10"))])

# ───────────────────────────────────────────
# Send to Discord (questions only)
# ───────────────────────────────────────────
discord_embed = {
    "embeds": [{
        "title": f"📚 Rewise Daily Quiz - {page_title}",
        "description": questions_only,
        "color": 5814783,  # Blue color
        "footer": {
            "text": f"📅 {datetime.now().strftime('%B %d, %Y')} • {mcq_count} Questions"
        }
    }]
}
requests.post(DISCORD_WEBHOOK, json=discord_embed)

# ───────────────────────────────────────────
# Append to Notion Rewise page (with answers)
# ───────────────────────────────────────────
append_to_rewise_formatted(page_title, full_with_answers, REWISE_PAGE_ID)

# ───────────────────────────────────────────
# Update tracking
# ───────────────────────────────────────────
update_page_tracking(TRACKING_PAGE_ID, pid, page_title, mcq_count)

print(f"✅ {mcq_count} MCQs generated from '{page_title}'")
print(f"   📤 Questions sent to Discord")
print(f"   📝 Full answers logged in Notion")
print(f"   📊 Tracking updated")
