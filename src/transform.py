"""
transform.py
------------
Cleans and standardizes the raw Online Retail II extract, splitting it
into three outputs rather than a simple clean/reject split:

  1. "clean"        - genuine product sales, ready for the warehouse
  2. "cancellations" - legitimate returns (Invoice starts with "C") - kept,
                        flagged, but excluded from gross sales totals
  3. "invalid"       - non-merchandise codes (postage, fees, adjustments)
                        and genuinely bad rows (missing critical fields,
                        non-positive price) - excluded and logged with a reason

Design choice: real transactional data has legitimate business events
(cancellations) that look like "bad data" but aren't. Treating them the
same as data-entry errors would be a modelling mistake, not just a coding
one - so they get their own category instead of being dropped or silently
mixed into sales.
"""

import logging
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Known non-merchandise stock codes found in this dataset (postage, fees,
# manual adjustments, samples) - not real product sales.
NON_MERCHANDISE_CODES = {
    "POST", "DOT", "M", "C2", "D", "S", "BANK CHARGES",
    "ADJUST", "AMAZONFEE", "PADS", "CRUK",
}


def transform_transactions(df: pd.DataFrame) -> dict:
    stats = {"input_rows": len(df)}
    df = df.copy()

    # 1. Standardize column names to snake_case for consistency downstream
    df = df.rename(columns={
        "Invoice": "invoice",
        "StockCode": "stock_code",
        "Description": "description",
        "Quantity": "quantity",
        "InvoiceDate": "invoice_date",
        "Price": "unit_price",
        "Customer ID": "customer_id",
        "Country": "country",
    })

    # 2. Parse types
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["stock_code"] = df["stock_code"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()

    # 3. Remove exact duplicate rows
    before = len(df)
    df = df.drop_duplicates(keep="first")
    stats["exact_duplicates_removed"] = before - len(df)

    # 4. Flag cancellations (Invoice starts with "C") - legitimate, not invalid
    df["is_cancellation"] = df["invoice"].str.startswith("C")

    # 5. Flag non-merchandise stock codes
    df["is_non_merchandise"] = df["stock_code"].isin(NON_MERCHANDISE_CODES)

    # 6. Flag genuinely invalid rows (bad data, not business events)
    invalid_reason = pd.Series([None] * len(df), index=df.index, dtype="object")
    invalid_reason[df["invoice_date"].isna()] = "invalid_date"
    invalid_reason[df["unit_price"] <= 0] = invalid_reason[df["unit_price"] <= 0].fillna("non_positive_price")
    invalid_reason[df["quantity"] == 0] = invalid_reason[df["quantity"] == 0].fillna("zero_quantity")
    invalid_reason[df["description"].isin(["nan", ""])] = invalid_reason[
        df["description"].isin(["nan", ""])
    ].fillna("missing_description")

    df["_invalid_reason"] = invalid_reason

    # --- Split into the three outputs ---
    invalid = df[df["_invalid_reason"].notna() & ~df["is_cancellation"]].copy()
    non_merch = df[df["is_non_merchandise"] & df["_invalid_reason"].isna() & ~df["is_cancellation"]].copy()
    cancellations = df[df["is_cancellation"] & df["_invalid_reason"].isna()].copy()

    clean = df[
        df["_invalid_reason"].isna() & ~df["is_non_merchandise"] & ~df["is_cancellation"]
    ].drop(columns=["_invalid_reason", "is_non_merchandise", "is_cancellation"]).copy()

    stats["invalid_rows"] = len(invalid)
    stats["non_merchandise_rows"] = len(non_merch)
    stats["cancellation_rows"] = len(cancellations)
    stats["clean_rows"] = len(clean)

    # 7. Derived column for analysis
    clean["gross_amount"] = (clean["quantity"] * clean["unit_price"]).round(2)
    clean["invoice_month"] = clean["invoice_date"].dt.to_period("M").astype(str)

    logger.info(
        "Transform complete: %s input -> %s clean, %s cancellations, %s non-merchandise, %s invalid",
        stats["input_rows"], stats["clean_rows"], stats["cancellation_rows"],
        stats["non_merchandise_rows"], stats["invalid_rows"],
    )

    invalid.to_csv(PROCESSED_DIR / "invalid_rows.csv", index=False)
    cancellations.to_csv(PROCESSED_DIR / "cancellations.csv", index=False)

    return {"clean": clean, "cancellations": cancellations, "invalid": invalid, "stats": stats}