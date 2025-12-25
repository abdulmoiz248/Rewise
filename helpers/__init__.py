"""
Rewise Helper Functions
Handles all Notion API interactions for fetching and appending content.
"""

import os
import requests
from typing import List, Dict, Any
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
