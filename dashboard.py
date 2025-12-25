"""
Dashboard Update Script
Updates the Rewise Dashboard with latest metrics
"""

import os
from dotenv import load_dotenv
from helpers import (
    get_database_pages,
    get_or_create_tracking_page
)
from dashboard_helpers import (
    get_or_create_dashboard_page,
    update_dashboard
)

load_dotenv()

def main():
    """Update the dashboard with latest metrics"""
    print("📊 Updating Rewise Dashboard...")
    
    # Get all pages and tracking page
    pages = get_database_pages()
    tracking_page_id = get_or_create_tracking_page()
    
    # Get or create dashboard
    dashboard_page_id = get_or_create_dashboard_page()
    
    # Update dashboard
    success = update_dashboard(dashboard_page_id, pages, tracking_page_id)
    
    if success:
        print("✅ Dashboard updated successfully!")
    else:
        print("❌ Failed to update dashboard")

if __name__ == "__main__":
    main()
