"""
Dashboard Helper Functions
Handles dashboard creation and metrics calculation
"""

import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Import from main helpers
from helpers import get_page_content, get_page_tracking_data


def get_or_create_dashboard_page() -> Optional[str]:
    """Find or create the Rewise Dashboard page in the database."""
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    res = requests.post(url, headers=HEADERS).json()
    pages = res.get("results", [])
    
    for p in pages:
        title_prop = p["properties"].get("Name") or p["properties"].get("Title")
        title = ""
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
        if title.lower() in [" rewise dashboard", "rewise dashboard"]:
            return p["id"]
    
    # Create page if not exists
    create_url = "https://api.notion.com/v1/pages"
    body = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": " Rewise Dashboard"}}]}
        }
    }
    new_page = requests.post(create_url, headers=HEADERS, json=body).json()
    return new_page["id"]


def calculate_dashboard_metrics(pages: List[Dict[str, Any]], tracking_page_id: str) -> Dict[str, Any]:
    """Calculate all metrics for the dashboard."""
    tracking_data = get_page_tracking_data(tracking_page_id)
    current_date = datetime.now()
    week_ago = current_date - timedelta(days=7)
    
    # Define special pages to skip
    SPECIAL_PAGES = [
        "rewise", 
        "review tracker", 
        "rewise dashboard",
        "rewise dashboard"
    ]
    
    # Filter out special pages
    regular_pages = []
    for page in pages:
        title_prop = page["properties"].get("Name") or page["properties"].get("Title")
        title = ""
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
        
        # Check if title matches any special page (case-insensitive)
        if not any(special.lower() in title.lower() or title.lower() in special.lower() for special in SPECIAL_PAGES):
            regular_pages.append(page)
    
    total_pages = len(regular_pages)
    
    # Pages reviewed this week
    pages_reviewed_this_week = 0
    recently_reviewed = []
    
    for page_id, data in tracking_data.items():
        last_reviewed = datetime.strptime(data["last_reviewed"], "%Y-%m-%d")
        if last_reviewed >= week_ago:
            pages_reviewed_this_week += 1
        
        # Get page title
        page_title = "Unknown"
        for page in regular_pages:
            if page["id"] == page_id:
                title_prop = page["properties"].get("Name") or page["properties"].get("Title")
                if title_prop and title_prop.get("title"):
                    page_title = title_prop["title"][0]["plain_text"]
                break
        
        recently_reviewed.append({
            "title": page_title,
            "date": data["last_reviewed"],
            "confidence": data["confidence"],
            "review_count": data["review_count"]
        })
    
    # Sort by date descending
    recently_reviewed.sort(key=lambda x: x["date"], reverse=True)
    
    # Pages never reviewed
    reviewed_page_ids = set(tracking_data.keys())
    never_reviewed = []
    for page in regular_pages:
        if page["id"] not in reviewed_page_ids:
            title_prop = page["properties"].get("Name") or page["properties"].get("Title")
            title = ""
            if title_prop and title_prop.get("title"):
                title = title_prop["title"][0]["plain_text"]
            never_reviewed.append(title)
    
    # Most overdue pages
    overdue_pages = []
    for page in regular_pages:
        page_id = page["id"]
        if page_id in tracking_data:
            last_reviewed = datetime.strptime(tracking_data[page_id]["last_reviewed"], "%Y-%m-%d")
            days_since_review = (current_date - last_reviewed).days
            
            title_prop = page["properties"].get("Name") or page["properties"].get("Title")
            title = ""
            if title_prop and title_prop.get("title"):
                title = title_prop["title"][0]["plain_text"]
            
            overdue_pages.append({
                "title": title,
                "days_overdue": days_since_review,
                "confidence": tracking_data[page_id]["confidence"]
            })
    
    # Sort by days overdue descending
    overdue_pages.sort(key=lambda x: x["days_overdue"], reverse=True)
    
    # Total MCQs generated
    total_mcqs = sum(data["review_count"] for data in tracking_data.values())
    
    # Average confidence
    avg_confidence = sum(data["confidence"] for data in tracking_data.values()) / len(tracking_data) if tracking_data else 0
    
    return {
        "total_pages": total_pages,
        "pages_reviewed_this_week": pages_reviewed_this_week,
        "never_reviewed_count": len(never_reviewed),
        "never_reviewed": never_reviewed[:10],  # Top 10
        "overdue_pages": overdue_pages[:10],  # Top 10
        "recently_reviewed": recently_reviewed[:10],  # Top 10
        "total_mcqs": total_mcqs,
        "avg_confidence": avg_confidence,
        "total_reviewed": len(tracking_data)
    }


def create_progress_bar(percentage: float, width: int = 20) -> str:
    """Create a visual progress bar using Unicode characters."""
    filled = int(percentage * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"{bar} {percentage:.1%}"


def create_bar_chart(data: List[tuple], max_width: int = 30) -> List[str]:
    """Create a text-based bar chart."""
    if not data:
        return []
    
    max_value = max(item[1] for item in data)
    chart_lines = []
    
    for label, value in data:
        bar_length = int((value / max_value) * max_width) if max_value > 0 else 0
        bar = "█" * bar_length
        chart_lines.append(f"{label}: {bar} {value}")
    
    return chart_lines


def update_dashboard(dashboard_page_id: str, pages: List[Dict[str, Any]], tracking_page_id: str) -> bool:
    """Update the dashboard with latest metrics. Clear existing content and rebuild."""
    # Get current blocks and delete them
    blocks = get_page_content(dashboard_page_id)
    for block in blocks:
        try:
            delete_url = f"https://api.notion.com/v1/blocks/{block['id']}"
            requests.delete(delete_url, headers=HEADERS)
        except:
            pass
    
    # Calculate metrics
    metrics = calculate_dashboard_metrics(pages, tracking_page_id)
    current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    # Build dashboard content
    url = f"https://api.notion.com/v1/blocks/{dashboard_page_id}/children"
    children = []
    
    # Header
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{
                "type": "text",
                "text": {"content": " Rewise Dashboard"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    # Last updated
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Last Updated: {current_date}"},
                "annotations": {"italic": True, "color": "gray"}
            }]
        }
    })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Key Metrics Section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "📈 Key Metrics"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    # Metric callouts
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "📄"},
            "color": "blue_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Total Pages: {metrics['total_pages']}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "🔁"},
            "color": "purple_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Pages Reviewed (This Week): {metrics['pages_reviewed_this_week']}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "✅"},
            "color": "green_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Total Reviewed: {metrics['total_reviewed']} ({(metrics['total_reviewed']/metrics['total_pages']*100) if metrics['total_pages'] > 0 else 0:.1f}%)"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "🕒"},
            "color": "orange_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Never Reviewed: {metrics['never_reviewed_count']}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "🧠"},
            "color": "pink_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Total MCQs Generated: {metrics['total_mcqs']}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"emoji": "📊"},
            "color": "yellow_background",
            "rich_text": [{
                "type": "text",
                "text": {"content": f"Average Confidence: {metrics['avg_confidence']:.1%}"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Visual Charts Section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": " Visual Analytics"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    # Review Progress Chart
    review_progress = (metrics['total_reviewed'] / metrics['total_pages'] * 100) if metrics['total_pages'] > 0 else 0
    progress_bar = create_progress_bar(metrics['total_reviewed'] / metrics['total_pages'] if metrics['total_pages'] > 0 else 0)
    
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"📈 Review Progress\n{progress_bar}"},
                "annotations": {"bold": True, "code": True}
            }]
        }
    })
    
    # Confidence Distribution
    confidence_bar = create_progress_bar(metrics['avg_confidence'])
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"🎯 Average Confidence\n{confidence_bar}"},
                "annotations": {"bold": True, "code": True}
            }]
        }
    })
    
    # Weekly Activity Chart
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "📅 Weekly Activity"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    # Create bar chart data for weekly reviews
    bar_chart_data = [
        ("This Week", metrics['pages_reviewed_this_week']),
        ("Total Reviewed", metrics['total_reviewed']),
        ("Never Reviewed", metrics['never_reviewed_count'])
    ]
    chart_lines = create_bar_chart(bar_chart_data)
    
    for line in chart_lines:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": line},
                    "annotations": {"code": True}
                }]
            }
        })
    
    # Review Distribution by Status
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": " Review Status Distribution"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    status_data = [
        ("✅ Reviewed", metrics['total_reviewed']),
        ("🕒 Never Reviewed", metrics['never_reviewed_count']),
        ("📉 Needs Review", len(metrics['overdue_pages']))
    ]
    status_chart = create_bar_chart(status_data)
    
    for line in status_chart:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": line},
                    "annotations": {"code": True}
                }]
            }
        })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Recently Reviewed Section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "🧠 Recently Reviewed"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    if metrics["recently_reviewed"]:
        for item in metrics["recently_reviewed"]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": f"{item['title']} - {item['date']} (Confidence: {item['confidence']:.0%}, Reviews: {item['review_count']})"}
                    }]
                }
            })
    else:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "No reviews yet. Start reviewing!"},
                    "annotations": {"italic": True}
                }]
            }
        })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Most Overdue Section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "📉 Most Overdue Pages"},
                "annotations": {"bold": True, "color": "red"}
            }]
        }
    })
    
    if metrics["overdue_pages"]:
        for item in metrics["overdue_pages"]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": f"{item['title']} - {item['days_overdue']} days ago (Confidence: {item['confidence']:.0%})"},
                        "annotations": {"color": "orange" if item['days_overdue'] > 7 else "default"}
                    }]
                }
            })
    else:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "All reviews are up to date!"},
                    "annotations": {"italic": True, "color": "green"}
                }]
            }
        })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Never Reviewed Section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "🕒 Never Reviewed Pages"},
                "annotations": {"bold": True}
            }]
        }
    })
    
    if metrics["never_reviewed"]:
        for page_title in metrics["never_reviewed"]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": page_title}
                    }]
                }
            })
    else:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "🎉 All pages have been reviewed!"},
                    "annotations": {"italic": True, "color": "green"}
                }]
            }
        })
    
    children.append({"object": "block", "type": "divider", "divider": {}})
    
    # Footer note
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "💡 Tip: This dashboard updates automatically each time you run the Rewise script."},
                "annotations": {"italic": True, "color": "gray"}
            }]
        }
    })
    
    # Split into chunks of 100 blocks (Notion API limit)
    chunk_size = 100
    for i in range(0, len(children), chunk_size):
        chunk = children[i:i + chunk_size]
        try:
            response = requests.patch(url, headers=HEADERS, json={"children": chunk})
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error updating dashboard chunk {i//chunk_size + 1}: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return False
    
    return True
