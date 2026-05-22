import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import bs4
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from scraper.browser import BrowserManager

# Constants
BIDS_URL = "https://bidplus.gem.gov.in/all-bids"
MAX_RETRIES = 3
TARGET_LISTINGS = 30
OUTPUT_DIR = Path("data/raw")
OUTPUT_FILE = OUTPUT_DIR / "listings.json"


def _clean_text(text: Optional[str]) -> str:
    """Helper method to clean extracted text."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _extract_bid_data(card: bs4.element.Tag) -> Dict[str, Any]:
    """Helper method to extract data from a single bid card."""
    bid_id = ""
    bid_no_link = card.select_one(".bid_no a")
    if bid_no_link:
        bid_id = _clean_text(bid_no_link.text)

    item_category = ""
    quantity = ""
    col_md_4_rows = card.select(".card-body .col-md-4 .row")
    if len(col_md_4_rows) > 0:
        # Items is in the first row
        items_a = col_md_4_rows[0].select_one("a[data-content]")
        if items_a and items_a.has_attr("data-content"):
            item_category = _clean_text(items_a["data-content"])
        else:
            # Fallback to text without "Items:"
            item_text = _clean_text(col_md_4_rows[0].text)
            item_category = item_text.replace("Items:", "").strip()

    if len(col_md_4_rows) > 1:
        # Quantity is in the second row
        qty_text = _clean_text(col_md_4_rows[1].text)
        quantity = qty_text.replace("Quantity:", "").strip()

    buyer_name = ""
    col_md_5_rows = card.select(".card-body .col-md-5 .row")
    if len(col_md_5_rows) > 1:
        # Buyer name is the text of the second row
        buyer_name = _clean_text(col_md_5_rows[1].get_text(separator=" "))

    # Start Date and End Date are in col-md-3, we'll try to get End Date as award_date placeholder
    award_date = ""
    end_date_span = card.select_one(".card-body .col-md-3 .end_date")
    if end_date_span:
        award_date = _clean_text(end_date_span.text)

    result_page_url = ""
    view_result_link = card.select_one("a[href*='getBidResultView'], a[href*='getSinglePacketResultView']")
    if view_result_link and view_result_link.has_attr("href"):
        result_page_url = "https://bidplus.gem.gov.in" + view_result_link["href"]

    # bid_value is not directly visible on the listing card for all bids
    bid_value = ""

    return {
        "bid_id": bid_id,
        "item_category": item_category,
        "buyer_name": buyer_name,
        "quantity": quantity,
        "bid_value": bid_value,
        "award_date": award_date,
        "result_page_url": result_page_url
    }


def _save_raw_html(html_content: str, page_num: int):
    """Save raw HTML snapshot for debugging."""
    snapshots_dir = OUTPUT_DIR / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = snapshots_dir / f"page_{page_num}.html"
    with open(snapshot_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.debug(f"Saved HTML snapshot to {snapshot_file}")


def _save_listings(listings: List[Dict[str, Any]]):
    """Save raw results to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(listings, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved {len(listings)} listings to {OUTPUT_FILE}")


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(PlaywrightTimeoutError),
    reraise=True
)
async def scrape_listings() -> List[Dict[str, Any]]:
    """
    Scrapes bid listings from the GeM Bid Portal.
    Navigates to the portal, applies filters, and extracts listings across pages.
    """
    logger.info("Initializing browser manager...")
    manager = BrowserManager(headless=True)
    all_listings = []
    
    try:
        page = await manager.start()
        
        logger.info(f"Navigating to {BIDS_URL}")
        await page.goto(BIDS_URL, wait_until="domcontentloaded")
        
        # Wait for the filter checkboxes to be available
        logger.info("Waiting for filters to load...")
        await page.wait_for_selector("#bidrastatus", state="visible", timeout=15000)
        
        # Apply filters
        logger.info("Applying filter: Status = Bid/RA")
        await page.click("#bidrastatus")
        
        # Wait for Awarded filter to become interactive/visible.
        # It's disabled by default, gets enabled via JS after checking #bidrastatus.
        logger.info("Applying filter: Outcome = Awarded")
        await page.wait_for_timeout(2000) # Give it a moment to enable
        await page.click("#bid_awarded", force=True)
        
        logger.info("Waiting for filtered results to load...")
        # Wait for the loader to disappear or the cards to refresh
        await page.wait_for_timeout(3000)
        await page.wait_for_selector(".card", state="visible", timeout=20000)
        
        current_page = 1
        
        while len(all_listings) < TARGET_LISTINGS:
            logger.info(f"Extracting listings from page {current_page}...")
            await manager.random_delay(1.0, 2.5)
            
            # Extract HTML
            html = await page.inner_html("body")
            _save_raw_html(html, current_page)
            
            # Parse with bs4
            soup = bs4.BeautifulSoup(html, "html.parser")
            cards = soup.select(".card")
            
            if not cards:
                logger.warning(f"No cards found on page {current_page}.")
                break
                
            logger.info(f"Found {len(cards)} cards on page {current_page}.")
            
            for card in cards:
                if len(all_listings) >= TARGET_LISTINGS:
                    break
                
                listing_data = _extract_bid_data(card)
                if listing_data["bid_id"]:
                    all_listings.append(listing_data)
            
            logger.info(f"Total listings collected so far: {len(all_listings)}")
            
            if len(all_listings) >= TARGET_LISTINGS:
                break
                
            # Handle Pagination
            next_button = page.locator("a.page-link.next")
            if await next_button.count() > 0 and await next_button.is_visible():
                logger.info("Navigating to next page...")
                await next_button.click()
                await page.wait_for_timeout(2000)
                await page.wait_for_selector(".card", state="visible", timeout=20000)
                current_page += 1
            else:
                logger.info("No more pages available.")
                break

    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        await manager.take_screenshot_on_error()
        raise e
    finally:
        await manager.stop()
        
    _save_listings(all_listings)
    return all_listings

if __name__ == "__main__":
    asyncio.run(scrape_listings())
