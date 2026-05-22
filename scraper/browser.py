import asyncio
import random
from pathlib import Path
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# A realistic User-Agent to help avoid basic bot detection
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class BrowserManager:
    """Async Playwright browser manager with evasion helpers."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        """Initialize playwright, browser, context, and page."""
        logger.info(f"Starting browser manager (headless={self.headless})...")
        self._playwright = await async_playwright().start()
        
        # Launch Chromium with arguments to disable some automation flags
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Setup context with a realistic user-agent and viewport
        self.context = await self.browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        
        self.page = await self.context.new_page()
        logger.info("Browser session started successfully.")
        return self.page

    async def stop(self):
        """Close all browser resources securely."""
        logger.info("Closing browser session...")
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser session closed.")

    @staticmethod
    async def random_delay(min_seconds: float = 1.5, max_seconds: float = 3.0):
        """
        Random delay helper to mimic human behavior and avoid bot detection.
        Waits for a random amount of time between min_seconds and max_seconds.
        """
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Sleeping for {delay:.2f} seconds...")
        await asyncio.sleep(delay)

    async def take_screenshot_on_error(self, filename: str = "error_screenshot.png"):
        """
        Helper to capture a screenshot of the current page when an error occurs.
        Saves the screenshot to the data/output/screenshots directory.
        """
        if self.page:
            try:
                # Ensure the screenshot output directory exists
                screenshots_dir = Path("data/output/screenshots")
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                
                filepath = screenshots_dir / filename
                await self.page.screenshot(path=filepath, full_page=True)
                logger.error(f"Error screenshot successfully saved to {filepath}")
            except Exception as e:
                logger.error(f"Failed to take error screenshot: {e}")
