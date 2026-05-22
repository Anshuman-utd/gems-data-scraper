import pandas as pd
import numpy as np
import json
from pathlib import Path
from loguru import logger
from typing import Dict, Any


OUTPUT_DIR = Path("data/output")


def export_csv(df: pd.DataFrame) -> None:
    """Export the final cleaned dataset to CSV."""
    csv_path = OUTPUT_DIR / "final_dataset.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"Exported CSV to {csv_path}")


def export_json(df: pd.DataFrame) -> None:
    """Export the final cleaned dataset to JSON."""
    json_path = OUTPUT_DIR / "final_dataset.json"
    # Pandas to_json safely handles NaNs and datetimes
    df.to_json(json_path, orient="records", indent=4, force_ascii=False, date_format="iso")
    logger.info(f"Exported JSON to {json_path}")


def calculate_bid_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate overall bid participation statistics."""
    stats = {}
    if "bid_id" not in df.columns:
        return stats
        
    total_bids = df["bid_id"].nunique()
    total_vendors = len(df)
    
    # Calculate bidders per bid
    bidders_per_bid = df.groupby("bid_id").size()
    avg_bidders = bidders_per_bid.mean() if not bidders_per_bid.empty else 0
    bids_above_3 = (bidders_per_bid > 3).sum()
    pct_above_3 = (bids_above_3 / total_bids * 100) if total_bids > 0 else 0
    
    stats.update({
        "total_bids": int(total_bids),
        "total_vendors": int(total_vendors),
        "avg_bidders_per_bid": round(float(avg_bidders), 2),
        "bids_above_3_bidders_pct": round(float(pct_above_3), 2)
    })
    return stats


def calculate_l1_l2_gap(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate the pricing gap between L1 and L2 vendors across bids."""
    stats = {"avg_l1_l2_gap": 0.0}
    if "bid_id" not in df.columns or "vendor_rank" not in df.columns or "vendor_price" not in df.columns:
        return stats
        
    gaps = []
    for bid_id, group in df.groupby("bid_id"):
        l1 = group[group["vendor_rank"] == "L1"]
        l2 = group[group["vendor_rank"] == "L2"]
        
        if not l1.empty and not l2.empty:
            l1_price = l1["vendor_price"].min()  # Use min to handle accidental duplicates safely
            l2_price = l2["vendor_price"].min()
            
            if pd.notna(l1_price) and pd.notna(l2_price) and l2_price >= l1_price:
                gap = l2_price - l1_price
                gaps.append(gap)
                
    if gaps:
        stats["avg_l1_l2_gap"] = round(float(np.mean(gaps)), 2)
        
    return stats


def analyze_repeat_winners(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect and count repeat winners across all bids."""
    stats = {"top_repeat_winners": {}}
    if "winner_name" not in df.columns or "bid_id" not in df.columns:
        return stats
        
    # Get one record per bid to count winners uniquely by bid
    bid_winners = df.drop_duplicates(subset=["bid_id"]).copy()
    bid_winners = bid_winners.dropna(subset=["winner_name"])
    
    if not bid_winners.empty:
        winner_counts = bid_winners["winner_name"].value_counts()
        top_5 = winner_counts.head(5).to_dict()
        stats["top_repeat_winners"] = {k: int(v) for k, v in top_5.items()}
        
    return stats


def analyze_competition(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze competition at the category level."""
    stats = {"most_competitive_categories": {}}
    
    cat_col = None
    if "item_category" in df.columns:
        cat_col = "item_category"
    elif "category" in df.columns:
        cat_col = "category"
        
    if not cat_col or "bid_id" not in df.columns:
        return stats
        
    # Calculate bidders per bid and aggregate by category
    bid_sizes = df.groupby(["bid_id", cat_col]).size().reset_index(name="bidders")
    
    if not bid_sizes.empty:
        cat_avg = bid_sizes.groupby(cat_col)["bidders"].mean().sort_values(ascending=False)
        top_cats = cat_avg.head(5).to_dict()
        stats["most_competitive_categories"] = {k: round(float(v), 2) for k, v in top_cats.items()}
        
    return stats


def summarize_anomalies(df: pd.DataFrame) -> Dict[str, Any]:
    """Summarize anomalies and data quality issues."""
    stats = {
        "duplicate_vendors": 0,
        "anomalies_detected": 0,
        "malformed_prices": 0
    }
    
    if "duplicate_vendor_flag" in df.columns:
        stats["duplicate_vendors"] = int(df["duplicate_vendor_flag"].sum())
        
    if "anomaly_flag" in df.columns:
        stats["anomalies_detected"] = int(df["anomaly_flag"].sum())
        
    if "vendor_price" in df.columns:
        stats["malformed_prices"] = int(df["vendor_price"].isna().sum())
        
    return stats


def generate_insights(df: pd.DataFrame) -> None:
    """
    Main orchestration function for analytics and reporting.
    Generates summary statistics, detects patterns, and exports the final data.
    """
    logger.info("Starting analytics and insights generation...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        # Generate Statistics
        bid_stats = calculate_bid_statistics(df)
        gap_stats = calculate_l1_l2_gap(df)
        winner_stats = analyze_repeat_winners(df)
        comp_stats = analyze_competition(df)
        anomaly_stats = summarize_anomalies(df)
        
        # Merge into final summary
        summary = {}
        summary.update(bid_stats)
        summary.update(gap_stats)
        summary.update(winner_stats)
        summary.update(comp_stats)
        summary.update(anomaly_stats)
        
        # Export files
        export_csv(df)
        export_json(df)
        
        summary_path = OUTPUT_DIR / "insights_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
        logger.info(f"Exported Insights Summary to {summary_path}")
        
        # Console Reporting
        print("\n" + "-"*48)
        print("SCRAPING & ANALYTICS SUMMARY")
        print("-"*48)
        print(f"Total Bids: {summary.get('total_bids', 0)}")
        print(f"Total Vendors: {summary.get('total_vendors', 0)}")
        print(f"Average Bidders Per Bid: {summary.get('avg_bidders_per_bid', 0)}")
        print(f"Average L1-L2 Gap: ₹{summary.get('avg_l1_l2_gap', 0):,.2f}")
        print(f"Duplicate Vendors: {summary.get('duplicate_vendors', 0)}")
        print(f"Anomalies Detected: {summary.get('anomalies_detected', 0)}")
        print("-"*48)
        
        top_winners = summary.get("top_repeat_winners", {})
        if top_winners:
            print("Top Repeat Winners:")
            for w, count in top_winners.items():
                print(f"  - {w}: {count} wins")
            print("-"*48)
            
        comp_cats = summary.get("most_competitive_categories", {})
        if comp_cats:
            print("Most Competitive Categories:")
            for c, avg in comp_cats.items():
                print(f"  - {c}: {avg} avg bidders")
            print("-"*48)
            
    except Exception as e:
        logger.error(f"Failed to generate insights: {e}")
        raise e
