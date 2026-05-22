from typing import Dict
from loguru import logger
from playwright.async_api import Page
import bs4

async def extract_buyer_details(page: Page) -> Dict[str, str]:
    """
    Extracts buyer details from the currently open bid result page.
    Uses text-based parsing on the page's HTML to be resilient to DOM structure changes.
    """
    logger.info("Extracting buyer details from the current page.")
    
    details = {
        "buyer_name": "",
        "address": "",
        "ministry": "",
        "department": "",
        "organisation": "",
        "office": "",
        "state": ""
    }
    
    try:
        # Get the full HTML to parse robustly with BeautifulSoup
        html_content = await page.content()
        soup = bs4.BeautifulSoup(html_content, "html.parser")
        
        # Look for the "Buyer Details" section
        buyer_details_header = soup.find(string=lambda t: t and "Buyer Details" in t)
        
        if not buyer_details_header:
            logger.warning("Could not find 'Buyer Details' text on the page.")
            return details
            
        # The section containing buyer details is likely a parent or ancestor of this header.
        # We will look for a container that has at least "Name:" and "Ministry:"
        container = buyer_details_header.parent
        while container and container.name != "body":
            text_content = container.get_text()
            if "Name:" in text_content and "Ministry:" in text_content:
                break
            container = container.parent
            
        if not container or container.name == "body":
            logger.warning("Could not find a valid container for Buyer Details.")
            return details
            
        # Extract text components
        # A common pattern is having label tags (e.g. <strong>, <label>) followed by value tags
        # We can normalize the text and extract values based on labels
        
        label_map = {
            "Name:": "buyer_name",
            "Address:": "address",
            "Ministry:": "ministry",
            "Department:": "department",
            "Organisation:": "organisation",
            "Office:": "office",
            "State:": "state"
        }
        
        # We extract all text elements inside the container in order
        texts = [t.strip() for t in container.stripped_strings]
        
        for i, text in enumerate(texts):
            for label_key, dict_key in label_map.items():
                if text == label_key or text.startswith(label_key):
                    # If the text is exactly the label, the value is the next item
                    if text == label_key and i + 1 < len(texts):
                        # The next text might be another label if the field is empty, so we check
                        next_text = texts[i+1]
                        if not any(next_text.startswith(lk) for lk in label_map.keys()):
                            details[dict_key] = next_text
                    # If the text starts with the label (e.g. "Name: John Doe")
                    elif text.startswith(label_key) and len(text) > len(label_key):
                        val = text[len(label_key):].strip()
                        details[dict_key] = val
                        
        logger.info("Successfully extracted buyer details.")
        
    except Exception as e:
        logger.error(f"Failed to extract buyer details: {str(e)}")
        
    return details
