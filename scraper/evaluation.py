from typing import List, Dict, Any, Optional
import bs4
from loguru import logger
from playwright.async_api import Page


def normalize_text(text: Optional[str]) -> str:
    """Strip whitespace, remove extra newlines, and normalize spacing."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def clean_price(price_text: Optional[str]) -> Optional[float]:
    """Remove ₹ symbol, commas, and convert to float safely."""
    if not price_text:
        return None
    cleaned = (
        price_text.replace("₹", "")
        .replace(",", "")
        .replace("INR", "")
        .replace("Rs", "")
        .replace("Rs.", "")
        .replace("Cr.", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        logger.debug(f"Failed to convert price to float: {price_text}")
        return None


def extract_table_headers(table: bs4.element.Tag) -> List[str]:
    """Dynamically detect and return headers from a table."""
    headers = []
    rows = table.find_all("tr")
    if not rows:
        return headers
    
    # Generally the first row contains the th or td elements functioning as headers
    header_cells = rows[0].find_all(["th", "td"])
    headers = [normalize_text(h.get_text()).lower() for h in header_cells]
    return headers


def parse_technical_evaluation(soup: bs4.BeautifulSoup) -> List[Dict[str, Any]]:
    """Parse the technical evaluation table."""
    results = []
    target_table = None
    
    for table in soup.find_all("table"):
        headers = extract_table_headers(table)
        # Technical evaluation tables typically have seller and status but no price
        if any("seller" in h for h in headers) and any("status" in h for h in headers) and not any("price" in h or "value" in h for h in headers):
            target_table = table
            break
            
    if not target_table:
        logger.warning("Technical evaluation table not found.")
        return results
        
    rows = target_table.find_all("tr")
    if len(rows) < 2:
        return results
        
    headers = extract_table_headers(target_table)
    try:
        seller_idx = next(i for i, h in enumerate(headers) if "seller" in h)
        status_idx = next(i for i, h in enumerate(headers) if h == "status" or (h.startswith("status") and "emd" not in h and "mii" not in h))
        remarks_idx = next((i for i, h in enumerate(headers) if "remark" in h or "reason" in h), None)
    except StopIteration:
        logger.warning(f"Could not map required columns in technical table headers: {headers}")
        return results
        
    data_rows = [row for row in rows[1:] if row.find_all(["td", "th"])]
    num_bidders = len(data_rows)
    
    for row in data_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) <= max(seller_idx, status_idx):
            continue
            
        vendor_name = normalize_text(cells[seller_idx].get_text())
        status_flag = normalize_text(cells[status_idx].get_text())
        remarks = normalize_text(cells[remarks_idx].get_text()) if remarks_idx is not None and len(cells) > remarks_idx else None
        
        if vendor_name:
            results.append({
                "vendor_name": vendor_name,
                "status_flag": status_flag,
                "remarks": remarks,
                "num_bidders": num_bidders
            })
            
    return results


def parse_financial_evaluation(soup: bs4.BeautifulSoup) -> List[Dict[str, Any]]:
    """Parse the financial evaluation table."""
    results = []
    target_table = None
    
    for table in soup.find_all("table"):
        headers = extract_table_headers(table)
        # Financial tables will have seller and price/value/amount or rank
        if any("seller" in h for h in headers) and (any("price" in h or "value" in h or "amount" in h for h in headers) or any("rank" in h for h in headers)):
            target_table = table
            break
            
    if not target_table:
        logger.warning("Financial evaluation table not found.")
        return results
        
    rows = target_table.find_all("tr")
    if len(rows) < 2:
        return results
        
    headers = extract_table_headers(target_table)
    try:
        seller_idx = next(i for i, h in enumerate(headers) if "seller" in h)
        price_idx = next((i for i, h in enumerate(headers) if "price" in h or "value" in h or "amount" in h), None)
        rank_idx = next((i for i, h in enumerate(headers) if "rank" in h or "position" in h), None)
    except StopIteration:
        logger.warning(f"Could not map seller column in financial table headers: {headers}")
        return results
        
    data_rows = [row for row in rows[1:] if row.find_all(["td", "th"])]
    
    for row in data_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) <= seller_idx:
            continue
            
        vendor_name = normalize_text(cells[seller_idx].get_text())
        vendor_price = clean_price(cells[price_idx].get_text()) if price_idx is not None and len(cells) > price_idx else None
        vendor_rank = normalize_text(cells[rank_idx].get_text()) if rank_idx is not None and len(cells) > rank_idx else None
        
        if vendor_name:
            results.append({
                "vendor_name": vendor_name,
                "vendor_price": vendor_price,
                "vendor_rank": vendor_rank
            })
            
    return results


async def extract_evaluation_data(page: Page) -> List[Dict[str, Any]]:
    """
    Extracts and merges technical and financial evaluation data from the current page.
    Assumes the page is already rendered and populated.
    """
    logger.info("Extracting evaluation data from current page...")
    html = await page.content()
    soup = bs4.BeautifulSoup(html, "html.parser")
    
    tech_data = parse_technical_evaluation(soup)
    fin_data = parse_financial_evaluation(soup)
    
    merged_results = []
    
    # If no data at all
    if not tech_data and not fin_data:
        logger.warning("No evaluation data could be extracted.")
        return merged_results

    # Lookup map for financial data
    fin_map = {item["vendor_name"].lower(): item for item in fin_data}
    
    # If only financial data exists
    if not tech_data and fin_data:
        num_bidders = len(fin_data)
        for fin in fin_data:
            merged_results.append({
                "vendor_name": fin["vendor_name"],
                "vendor_rank": fin["vendor_rank"],
                "vendor_price": fin["vendor_price"],
                "status_flag": None,
                "remarks": None,
                "num_bidders": num_bidders
            })
        logger.info(f"Successfully extracted {len(merged_results)} evaluation records (Financial only).")
        return merged_results

    # Default merge using technical data as the base
    for tech in tech_data:
        vendor_lower = tech["vendor_name"].lower()
        fin_info = fin_map.get(vendor_lower, {})
        
        # Fallback partial match if exact match fails
        if not fin_info:
            for fin_vendor, fin_obj in fin_map.items():
                if vendor_lower in fin_vendor or fin_vendor in vendor_lower:
                    fin_info = fin_obj
                    break
        
        merged_results.append({
            "vendor_name": tech["vendor_name"],
            "vendor_rank": fin_info.get("vendor_rank"),
            "vendor_price": fin_info.get("vendor_price"),
            "status_flag": tech["status_flag"],
            "remarks": tech["remarks"],
            "num_bidders": tech["num_bidders"]
        })
        
    logger.info(f"Successfully extracted {len(merged_results)} evaluation records.")
    return merged_results
