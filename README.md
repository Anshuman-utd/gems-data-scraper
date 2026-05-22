# GeM Procurement Data Scraping & Analysis Pipeline

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![Playwright](https://img.shields.io/badge/Playwright-Async-green)
![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-orange)

## 1. Project Overview

This project is an internship assignment developed for **GemEdge**. It is an end-to-end data scraping and analytics pipeline designed to extract, clean, and analyze public procurement bid data from the **GeM (Government e-Marketplace)** portal. 

The primary goals of this assignment are to demonstrate resilient system design, robust DOM parsing, defensive data validation, and meaningful anomaly detection. The pipeline extracts detailed records—spanning from high-level bid listings down to vendor-specific technical and financial evaluations—and exports them as analysis-ready CSV and JSON datasets accompanied by procurement insights.

## 2. Features

- **Asynchronous Scraping**: Utilizes `asyncio` and `Playwright` for high-performance, non-blocking browser navigation.
- **Dynamic Pagination & Filtering**: Interacts with complex, JavaScript-rendered tables and dynamically applies bid outcome filters.
- **Deep-Dive Evaluation Extraction**: Safely traverses DOM layers to extract granular technical qualifications and financial rankings for individual vendors.
- **Defensive Data Cleaning**: Employs vectorized pandas operations to normalize whitespace, format currency, detect duplicate vendors, and standardize dates.
- **Intelligent Anomaly Detection**: Flags suspicious bidding patterns (e.g., winner not offering the lowest price, missing L1 vendors).
- **Automated Checkpointing**: Built-in resume capability to seamlessly recover from interruptions without duplicate processing.
- **Structured Logging**: Uses `loguru` to generate comprehensive, highly-readable console reporting and error tracing.
- **Dual Format Exports**: Fully automated pipeline outputting `CSV`, `JSON`, and statistical summaries.

## 3. Tech Stack

- **Core**: Python 3.11+
- **Browser Automation**: `Playwright` (Async API)
- **HTML Parsing**: `BeautifulSoup4`
- **Data Engineering**: `pandas`, `numpy`
- **Resilience & Orchestration**: `tenacity` (exponential backoff)
- **Logging**: `loguru`
- **Configuration Management**: `python-dotenv`

## 4. Architecture / Pipeline Flow

```text
[START]
   │
   ├── 1. Listing Scraper (Navigates portal & extracts high-level bid records)
   │
   ├── 2. Bid Result Extraction (Traverses individual bid URLs for buyer metadata)
   │
   ├── 3. Evaluation Extraction (Parses Technical & Financial tables per vendor)
   │
   ├── 4. Data Cleaning (Normalizes text, coerces datatypes, identifies duplicates)
   │
   ├── 5. Insights Generation (Calculates procurement analytics & aggregations)
   │
   └── 6. Export (Saves cleaned structures to CSV/JSON)
   │
[END]
```

## 5. Folder Structure

```text
gem-procurement-scraper/
│
├── analysis/
│   └── insights.py           # Statistical aggregation and file exports
│
├── data/
│   ├── output/               # Pipeline execution artifacts (CSV, JSON, Checkpoints)
│   └── raw/                  # Snapshot storage and raw listing caches
│
├── scraper/
│   ├── browser.py            # Headless browser lifecycle and evasion configuration
│   ├── listing.py            # High-level bid directory scraping and pagination
│   ├── bid_result.py         # Buyer metadata and technical evaluation extraction
│   ├── evaluation.py         # Financial evaluation parsing and vendor merging
│   └── cleaner.py            # Pandas-based cleaning, validation, and anomaly flagging
│                   
├── requirements.txt          # Python dependencies
├── main.py                   # Master orchestration script
└── README.md                 # Project documentation
```

## 6. Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/gem-procurement-scraper.git
   cd gem-procurement-scraper
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install Python requirements**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

5. **Configure environment variables** (Optional):
   ```bash
   cp .env.example .env
   # Update the .env file with your specific configurations if needed
   ```

## 7. How to Run

Execute the pipeline via the master orchestrator `main.py`. The script provides CLI arguments to configure the execution dynamically.

**Run the full pipeline seamlessly (headless mode):**
```bash
python main.py
```

**Run for a specific number of bids:**
```bash
python main.py --max-bids 30
```

**Resume an interrupted session:**
```bash
python main.py --max-bids 100 --resume
```

**Run in headed mode (for debugging):**
```bash
python main.py --headless false
```

## 8. Output Files

All output artifacts are generated within the `data/output/` directory:

- `final_dataset.csv`: The complete, flattened, and cleaned dataset ready for tabular analysis or database ingestion.
- `final_dataset.json`: A pretty-printed, records-oriented JSON dataset preserving nested schemas and safe unicode formatting.
- `insights_summary.json`: High-level dictionary containing aggregated analytical metadata.
- `checkpoint.json`: Incremental state file used to resume interrupted scraping jobs.
- `failed_bids.json`: A log of specific bid URLs that threw extraction errors, preserved for pipeline debugging.

## 9. Data Cleaning & Validation

The `cleaner.py` module strictly enforces data integrity before analysis:

- **Vendor Normalization**: Eliminates erratic spacing, applies uppercase standardization, and handles malformed `null` equivalents defensively.
- **Currency Standardization**: Strips region-specific currency strings (e.g., `"₹"`, `"Cr."`, `"Rs."`) and executes safe float conversions.
- **Duplicate Vendor Detection**: Flags `duplicate_vendor_flag` for constraints where a `vendor_name` appears multiple times for the same `bid_id`.
- **Anomaly Detection**: Generates a boolean `anomaly_flag` alongside an `anomaly_reason` string if records break business logic (e.g., missing L1 vendors, negative prices, or instances where the declared winner's price exceeds the minimum calculated vendor price).
- **Malformed Data Handling**: Uses safe `.fillna()` and `.dropna()` protocols to ensure missing evaluations never crash the aggregation pipeline.

## 10. Analytics Generated

The `insights.py` module computes professional statistics outputted directly to the console and summary files:

- **Competition Density**: Calculates the average number of bidders per bid and identifies the percentage of bids featuring more than 3 participants.
- **Pricing Dynamics**: Analyzes the monetary gap between the winning L1 vendor and the runner-up L2 vendor, calculating average discrepancies.
- **Repeat Winner Analysis**: Groups historical bid awards to identify and rank the top 5 frequently winning vendors across the dataset.
- **Category Intelligence**: Aggregates procurement intensity to highlight the most highly competitive item categories.

## 11. Challenges Faced

1. **Inconsistent Table Structures**: Evaluation tables frequently altered their column arrangements or entirely omitted financial disclosures depending on the procurement phase. Handled via dynamic header cross-referencing rather than brittle XPath indices.
2. **Dynamic Rendering**: Heavy reliance on JavaScript for filter initialization required explicit `wait_for_selector` logic rather than standard HTTP requests.
3. **Anti-Bot Defenses**: Addressed using random timeout intervals, customized user agents, and headless evasion flags configured in the `BrowserManager`.
4. **Malformed Rows**: Gracefully swallowed using `BeautifulSoup`'s defensive extraction logic and `pandas` safe numeric coercions.

## 12. Future Improvements

- **Database Integration**: Migrate `CSV`/`JSON` exports to an automated `PostgreSQL` or `MongoDB` ingestion pipeline.
- **Distributed Scraping**: Implement a queueing system (e.g., `Celery` + `Redis`) to distribute bid extraction across multiple browser workers.
- **Dashboard Visualization**: Integrate `Streamlit` or `Dash` to visualize anomaly trends and category competition dynamically.
- **Automated Scheduling**: Containerize via `Docker` and deploy to a standard `cron` or `Airflow` scheduler for continuous monitoring.

## 13. Disclaimer

This project was built strictly as an educational/internship assignment. It interacts with public procurement data. The scraping architecture utilizes rate-limiting and random delays to interact respectfully with the GeM portal's infrastructure.
