"""
Rewise Helper Functions
Handles all Notion API interactions for fetching and appending content.
"""

import os
import requests
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}


def get_database_pages() -> List[Dict[str, Any]]:
    """
    Fetch all pages from the Notion database.
    
    Returns:
        List of page objects from the database
    """
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    
    try:
        response = requests.post(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching database pages: {e}")
        return []


def get_page_content(page_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all blocks (content) from a specific Notion page.
    
    Args:
        page_id: The ID of the Notion page
        
    Returns:
        List of block objects from the page
    """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching page content: {e}")
        return []


def extract_text(block: Dict[str, Any]) -> str:
    """
    Extract plain text from a Notion block.
    
    Args:
        block: A Notion block object
        
    Returns:
        Extracted text string
    """
    block_type = block.get("type", "")
    
    if not block_type:
        return ""
    
    # Check if rich_text exists in the block type
    if block_type in block and "rich_text" in block[block_type]:
        return "".join(
            text.get("plain_text", "")
            for text in block[block_type]["rich_text"]
        )
    
    return ""


def append_to_rewise(content: str, rewise_page_id: str = None) -> bool:
    """
    Append content to the Rewise page in Notion.
    
    Args:
        content: The text content to append (will be converted to Notion blocks)
        rewise_page_id: The ID of the Rewise page (optional, can be set via env var)
        
    Returns:
        True if successful, False otherwise
    """
    # Get the Rewise page ID from parameter or environment
    if not rewise_page_id:
        rewise_page_id = os.getenv("REWISE_PAGE_ID")
    
    if not rewise_page_id:
        print("❌ Error: REWISE_PAGE_ID not provided")
        return False
    
    url = f"https://api.notion.com/v1/blocks/{rewise_page_id}/children"
    
    # Split content into lines and create blocks
    lines = content.split("\n")
    children = []
    
    for line in lines:
        if line.strip():
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": line
                            }
                        }
                    ]
                }
            })
    
    # Add a divider for separation
    children.append({
        "object": "block",
        "type": "divider",
        "divider": {}
    })
    
    try:
        response = requests.patch(url, headers=HEADERS, json={"children": children})
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error appending to Rewise page: {e}")
        return False


def get_or_create_tracking_page() -> Optional[str]:
    """
    Find or create the Review Tracker page in the database.
    
    Returns:
        Page ID of the tracking page
    """
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    res = requests.post(url, headers=HEADERS).json()
    pages = res.get("results", [])
    
    for p in pages:
        title_prop = p["properties"].get("Name") or p["properties"].get("Title")
        title = ""
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
        if title.lower() == "review tracker":
            return p["id"]
    
    # Create page if not exists
    create_url = "https://api.notion.com/v1/pages"
    body = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": "Review Tracker"}}]}
        }
    }
    new_page = requests.post(create_url, headers=HEADERS, json=body).json()
    return new_page["id"]


def get_page_tracking_data(tracking_page_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse tracking data from the Review Tracker page.
    
    Returns:
        Dictionary mapping page_id to tracking info (last_reviewed, confidence, review_count)
    """
    blocks = get_page_content(tracking_page_id)
    tracking_data = {}
    
    for block in blocks:
        text = extract_text(block)
        # Format: page_id|last_reviewed|confidence|review_count
        if "|" in text:
            parts = text.split("|")
            if len(parts) >= 4:
                page_id = parts[0].strip()
                tracking_data[page_id] = {
                    "last_reviewed": parts[1].strip(),
                    "confidence": float(parts[2].strip()) if parts[2].strip() else 0.0,
                    "review_count": int(parts[3].strip()) if parts[3].strip() else 0
                }
    
    return tracking_data


def update_page_tracking(tracking_page_id: str, page_id: str, page_title: str, mcq_count: int):
    """
    Update tracking information for a reviewed page.
    """
    # Get current tracking data
    tracking_data = get_page_tracking_data(tracking_page_id)
    
    # Update or create entry for this page
    current_date = datetime.now().strftime("%Y-%m-%d")
    if page_id in tracking_data:
        review_count = tracking_data[page_id]["review_count"] + 1
        confidence = min(tracking_data[page_id]["confidence"] + 0.1, 1.0)
    else:
        review_count = 1
        confidence = 0.1
    
    # Create formatted entry
    entry = f"{page_id}|{current_date}|{confidence:.2f}|{review_count}|{page_title}|{mcq_count} MCQs"
    
    # Append to tracking page
    url = f"https://api.notion.com/v1/blocks/{tracking_page_id}/children"
    children = [{
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": entry}
            }]
        }
    }]
    
    try:
        requests.patch(url, headers=HEADERS, json={"children": children})
    except Exception as e:
        print(f"❌ Error updating tracking: {e}")


def select_page_for_review(pages: List[Dict[str, Any]], tracking_page_id: str) -> Optional[Dict[str, Any]]:
    """
    Intelligently select a page for review based on:
    - Last reviewed date (prioritize older)
    - Confidence score (prioritize lower confidence)
    - Never reviewed pages (highest priority)
    
    Returns:
        Selected page object
    """
    if not pages:
        return None
    
    tracking_data = get_page_tracking_data(tracking_page_id)
    current_date = datetime.now()
    
    # Score each page
    page_scores = []
    for page in pages:
        page_id = page["id"]
        
        # Skip special pages
        title_prop = page["properties"].get("Name") or page["properties"].get("Title")
        title = ""
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
        
        if title.lower() in ["rewise", "review tracker"]:
            continue
        
        if page_id in tracking_data:
            # Calculate days since last review
            last_reviewed = datetime.strptime(tracking_data[page_id]["last_reviewed"], "%Y-%m-%d")
            days_since_review = (current_date - last_reviewed).days
            confidence = tracking_data[page_id]["confidence"]
            
            # Score: higher is better (more days + lower confidence = higher score)
            score = days_since_review * 10 + (1.0 - confidence) * 50
        else:
            # Never reviewed = highest score
            score = 1000
        
        page_scores.append((score, page))
    
    if not page_scores:
        return None
    
    # Sort by score (descending) and return top
    page_scores.sort(key=lambda x: x[0], reverse=True)
    return page_scores[0][1]


def clean_ai_response(text: str) -> str:
    """
    Remove conversational text from AI responses.
    Keeps only the actual MCQs.
    """
    # Remove common AI intro phrases
    patterns = [
        r"^.*?(?:here are|here's|i've generated|i've created|sure|okay|alright).*?(?:\n|:)",
        r"^.*?(?:top \d+|following \d+).*?mcqs?.*?(?:\n|:)",
    ]
    
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    return cleaned.strip()


def parse_mcqs(text: str) -> Tuple[str, str]:
    """
    Parse MCQs to separate questions from answers.
    
    Returns:
        (questions_only, full_with_answers)
    """
    lines = text.split("\n")
    questions_lines = []
    full_lines = []
    
    skip_next = False
    for line in lines:
        full_lines.append(line)
        
        # Skip answer and explanation lines for Discord
        if skip_next:
            if line.strip().startswith(("Explanation:", "Explanation -")):
                skip_next = False
            continue
        
        if line.strip().startswith(("Answer:", "Answer -", "Correct Answer:")):
            skip_next = True
            continue
        
        questions_lines.append(line)
    
    return "\n".join(questions_lines), "\n".join(full_lines)


def append_to_rewise_formatted(page_title: str, mcqs_with_answers: str, rewise_page_id: str) -> bool:
    """
    Append formatted MCQs with proper Notion blocks (headings, paragraphs).
    """
    if not rewise_page_id:
        print("❌ Error: REWISE_PAGE_ID not provided")
        return False
    
    url = f"https://api.notion.com/v1/blocks/{rewise_page_id}/children"
    children = []
    
    # Add heading with date and page title
    current_date = datetime.now().strftime("%B %d, %Y")
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"📚 {page_title}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    # Add date
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"📅 {current_date}"},
                "annotations": {"italic": True, "color": "gray"}
            }]
        }
    })
    
    # Add MCQs content
    lines = mcqs_with_answers.split("\n")
    for line in lines:
        if line.strip():
            # Check if it's a question line
            is_question = line.strip().startswith(("Q", "Question"))
            is_answer = line.strip().startswith(("Answer:", "Correct Answer:"))
            is_explanation = line.strip().startswith("Explanation:")
            
            annotations = {}
            if is_question:
                annotations = {"bold": True}
            elif is_answer:
                annotations = {"bold": True, "color": "green"}
            elif is_explanation:
                annotations = {"italic": True, "color": "gray"}
            
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": line},
                        "annotations": annotations
                    }]
                }
            })
    
    # Add divider
    children.append({
        "object": "block",
        "type": "divider",
        "divider": {}
    })
    
    try:
        response = requests.patch(url, headers=HEADERS, json={"children": children})
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error appending to Rewise page: {e}")
        return False
