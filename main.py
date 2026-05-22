import asyncio
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from loguru import logger

from scraper.browser import BrowserManager
from scraper.listing import scrape_listings
from scraper.bid_result import extract_buyer_details
from scraper.evaluation import extract_evaluation_data
from scraper.cleaner import clean_pipeline
from analysis.insights import generate_insights


OUTPUT_DIR = Path("data/output")
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"
FAILED_BIDS_FILE = OUTPUT_DIR / "failed_bids.json"


def load_checkpoint() -> List[Dict[str, Any]]:
    """Load previously processed bids if resuming."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Checkpoint file corrupted. Starting fresh.")
    return []


def save_checkpoint(data: List[Dict[str, Any]]) -> None:
    """Save processed bids incrementally."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def save_failed_bids(failed_bids: List[Dict[str, Any]]) -> None:
    """Save failed bids for tracking."""
    if not failed_bids:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAILED_BIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(failed_bids, f, indent=4, ensure_ascii=False)


async def process_single_bid(page, bid: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Process evaluation and result details for a single bid.
    Navigates to the bid result URL and merges buyer metadata with vendor evaluations.
    """
    url = bid.get("result_page_url")
    if not url:
        raise ValueError("Missing result_page_url")
        
    await page.goto(url, wait_until="domcontentloaded")
    
    # Extract bid-level metadata (buyer details)
    buyer_info = await extract_buyer_details(page)
    
    # Extract vendor-level evaluation data
    eval_data = await extract_evaluation_data(page)
    
    # Derive global winner details from the evaluation data (L1 vendor)
    winner_name = None
    winner_price = None
    for vendor in eval_data:
        if vendor.get("vendor_rank") == "L1":
            winner_name = vendor.get("vendor_name")
            winner_price = vendor.get("vendor_price")
            break
            
    # Merge everything
    merged_records = []
    for vendor in eval_data:
        record = bid.copy()
        record.update(buyer_info)
        record.update(vendor)
        record["winner_name"] = winner_name
        record["winner_price"] = winner_price
        merged_records.append(record)
        
    return merged_records


async def run_pipeline(headless: bool, max_bids: int, resume: bool):
    """
    Main orchestration pipeline orchestrating the complete scraping workflow:
    1. Listings -> 2. Details -> 3. Cleaner -> 4. Insights
    """
    logger.info(f"Starting pipeline (headless={headless}, max_bids={max_bids}, resume={resume})")
    
    # ==========================================
    # Phase 1: Scrape Listings
    # ==========================================
    logger.info("=== STEP 1: Scrape Listings ===")
    listings = await scrape_listings()
    if max_bids > 0:
        listings = listings[:max_bids]
        
    logger.info(f"Retrieved {len(listings)} listings to process.")
    
    # ==========================================
    # Phase 2: Resume / Checkpoint Setup
    # ==========================================
    processed_records = []
    processed_bid_ids = set()
    failed_bids = []
    
    if resume:
        checkpoint_data = load_checkpoint()
        if checkpoint_data:
            processed_records = checkpoint_data
            processed_bid_ids = {r.get("bid_id") for r in processed_records if r.get("bid_id")}
            logger.info(f"Resuming: Loaded {len(processed_records)} vendor records across {len(processed_bid_ids)} bids from checkpoint.")
    
    # ==========================================
    # Phase 3: Extract Details (Results + Evaluation)
    # ==========================================
    logger.info("=== STEP 2: Extract Bid Results & Evaluations ===")
    manager = BrowserManager(headless=headless)
    
    try:
        page = await manager.start()
        
        for i, bid in enumerate(listings, 1):
            bid_id = bid.get("bid_id")
            
            if bid_id in processed_bid_ids:
                logger.info(f"[{i}/{len(listings)}] Skipping already processed bid {bid_id}")
                continue
                
            logger.info(f"[{i}/{len(listings)}] Processing bid {bid_id}...")
            
            try:
                # Add random delay to prevent blocking
                await manager.random_delay(1.5, 3.5)
                
                vendor_records = await process_single_bid(page, bid)
                
                if vendor_records:
                    processed_records.extend(vendor_records)
                    processed_bid_ids.add(bid_id)
                    logger.info(f"[{i}/{len(listings)}] Extracted {len(vendor_records)} vendor(s) for bid {bid_id}")
                else:
                    logger.warning(f"[{i}/{len(listings)}] No evaluation data found for bid {bid_id}")
                
                # Checkpoint progress incrementally
                save_checkpoint(processed_records)
                
            except Exception as e:
                logger.error(f"[{i}/{len(listings)}] Failed to process bid {bid_id}: {str(e)}")
                failed_bids.append({
                    "bid_id": bid_id,
                    "url": bid.get("result_page_url"),
                    "error": str(e)
                })
                
    finally:
        logger.info("Closing browser gracefully...")
        await manager.stop()
        
    save_failed_bids(failed_bids)
    
    if not processed_records:
        logger.error("No data extracted. Aborting cleaning and insights.")
        return
        
    # ==========================================
    # Phase 4: Clean Data
    # ==========================================
    logger.info("=== STEP 3: Clean Dataset ===")
    df = pd.DataFrame(processed_records)
    cleaned_df = clean_pipeline(df)
    
    # ==========================================
    # Phase 5: Generate Insights & Export
    # ==========================================
    logger.info("=== STEP 4: Generate Insights & Export ===")
    generate_insights(cleaned_df)
    
    logger.info("Pipeline completed successfully.")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="GeM Procurement Scraper Pipeline")
    parser.add_argument("--headless", type=str, default="true", help="Run browser in headless mode (true/false)")
    parser.add_argument("--max-bids", type=int, default=0, help="Maximum number of bids to process (0 for all)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint file")
    
    args = parser.parse_args()
    
    headless = args.headless.lower() in ("true", "1", "yes")
    
    try:
        asyncio.run(run_pipeline(headless=headless, max_bids=args.max_bids, resume=args.resume))
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
    except Exception as e:
        logger.critical(f"Pipeline crashed: {e}")


if __name__ == "__main__":
    main()
