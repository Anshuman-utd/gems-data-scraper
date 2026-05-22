import pandas as pd
import numpy as np
from loguru import logger
from typing import List


def clean_vendor_names(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """
    Normalize vendor names by stripping whitespace, uppercase, and removing extra spaces.
    Example: "MAX  SECURE SOFTWARE" -> "MAX SECURE SOFTWARE"
    """
    for col in columns:
        if col in df.columns:
            # Replace multiple spaces with a single space, strip, and uppercase
            df[col] = df[col].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
            # Restore NaNs where it was 'NAN' or 'NONE'
            df[col] = df[col].replace({'NAN': np.nan, 'NONE': np.nan, '': np.nan})
    return df


def clean_prices(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """
    Safely convert price strings to floats, removing currency symbols and commas.
    Example: "₹1,25,000" -> 125000.0
    """
    for col in columns:
        if col in df.columns:
            # Convert to string to safely use string methods
            s = df[col].astype(str)
            # Remove common currency symbols and formatting characters
            for token in ['₹', ',', 'Rs.', 'Rs', 'Cr.', 'Cr', 'INR']:
                s = s.str.replace(token, '', regex=False)
            # Remove any remaining whitespace
            s = s.str.replace(r'\s+', '', regex=True)
            # Convert to numeric, coercing any unparseable strings to NaN
            df[col] = pd.to_numeric(s, errors='coerce')
    return df


def standardize_dates(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Convert date strings to consistent pandas datetime format safely."""
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Handle missing values gracefully based on business rules."""
    if "remarks" in df.columns:
        df["remarks"] = df["remarks"].fillna("")
    if "vendor_rank" in df.columns:
        df["vendor_rank"] = df["vendor_rank"].fillna("Unknown")
    return df


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Detect duplicate vendors within the same bid."""
    if "bid_id" in df.columns and "vendor_name" in df.columns:
        # Flag duplicates keeping all instances flagged so we can identify anomalies
        df["duplicate_vendor_flag"] = df.duplicated(subset=["bid_id", "vendor_name"], keep=False)
        dupes_count = df["duplicate_vendor_flag"].sum()
        logger.info(f"Detected {dupes_count} duplicate vendor records across bids.")
    else:
        df["duplicate_vendor_flag"] = False
        logger.warning("Columns 'bid_id' or 'vendor_name' missing. Cannot detect duplicate vendors.")
    return df


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Flag anomalous records based on logical validation rules."""
    df["anomaly_flag"] = False
    anomaly_reasons = pd.Series("", index=df.index)
    
    # 1. Check for negative or zero prices
    price_cols = [c for c in ["bid_value", "winner_price", "vendor_price"] if c in df.columns]
    for col in price_cols:
        mask = df[col] <= 0
        df.loc[mask, "anomaly_flag"] = True
        anomaly_reasons[mask] += f"Negative/Zero {col}; "
        
    # 2. Check if winner is not the lowest price
    if "bid_id" in df.columns and "winner_price" in df.columns and "vendor_price" in df.columns:
        # Calculate minimum vendor price per bid
        min_prices = df.groupby("bid_id")["vendor_price"].transform("min")
        # Winner price should theoretically be <= min vendor price
        # Adding a small tolerance for floating point inaccuracies
        mask = (df["winner_price"] > min_prices + 0.01) & df["winner_price"].notna() & min_prices.notna()
        df.loc[mask, "anomaly_flag"] = True
        anomaly_reasons[mask] += "Winner price > minimum vendor price; "
        
    # 3. Missing L1 vendor
    if "bid_id" in df.columns and "vendor_rank" in df.columns:
        # Group by bid_id, check if any row has 'L1'
        has_l1 = df.groupby("bid_id")["vendor_rank"].transform(lambda x: (x == "L1").any())
        mask = ~has_l1
        df.loc[mask, "anomaly_flag"] = True
        anomaly_reasons[mask] += "Missing L1 vendor in bid; "
        
    df["anomaly_reason"] = anomaly_reasons.str.strip("; ")
    anomalies_count = df["anomaly_flag"].sum()
    logger.info(f"Detected {anomalies_count} anomalous records.")
    
    return df


def clean_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main cleaning pipeline orchestrator.
    Processes the raw merged DataFrame to produce analysis-ready data.
    """
    logger.info(f"Starting cleaning pipeline for {len(df)} records.")
    
    # Create a copy to avoid modifying the original dataframe in place
    df_clean = df.copy()
    
    # 1. Clean Text
    vendor_cols = ["winner_name", "vendor_name"]
    df_clean = clean_vendor_names(df_clean, vendor_cols)
    
    # Explicitly create normalized_vendor_name as required
    if "vendor_name" in df_clean.columns:
        df_clean["normalized_vendor_name"] = df_clean["vendor_name"]
        
    # Normalize status values
    if "status_flag" in df_clean.columns:
        df_clean["status_flag"] = df_clean["status_flag"].astype(str).str.strip().str.title()
        df_clean["status_flag"] = df_clean["status_flag"].replace({'Nan': np.nan, 'None': np.nan})

    # 2. Clean Prices
    price_cols = ["bid_value", "winner_price", "vendor_price"]
    df_clean = clean_prices(df_clean, price_cols)
    
    # 3. Standardize Dates
    date_cols = ["award_date", "bid_end_date"]
    df_clean = standardize_dates(df_clean, date_cols)
    
    # 4. Handle Missing Values
    df_clean = handle_missing_values(df_clean)
    
    # 5. Detect Duplicates
    df_clean = detect_duplicates(df_clean)
    
    # 6. Detect Anomalies
    df_clean = detect_anomalies(df_clean)
    
    # Generate Summary Report
    logger.info("=== Cleaning Pipeline Summary ===")
    logger.info(f"Total Rows processed: {len(df_clean)}")
    
    if "duplicate_vendor_flag" in df_clean.columns:
        logger.info(f"Duplicate Vendor Rows: {df_clean['duplicate_vendor_flag'].sum()}")
        
    if "anomaly_flag" in df_clean.columns:
        logger.info(f"Anomalous Rows: {df_clean['anomaly_flag'].sum()}")
    
    for col in price_cols:
        if col in df_clean.columns:
            missing = df_clean[col].isna().sum()
            logger.info(f"Missing/Malformed {col}: {missing} / {len(df_clean)}")
            
    logger.info("Cleaning complete. Data is ready for analysis.")
    
    return df_clean
