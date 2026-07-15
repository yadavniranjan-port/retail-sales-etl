"""
load.py
-------
Loads cleaned data into a DuckDB warehouse using a star schema adapted for
the Online Retail II dataset: fact_sales, fact_cancellations, dim_product,
dim_country, dim_date. DuckDB stands in for a cloud warehouse
(BigQuery/Snowflake) so the pipeline runs with zero external credentials.
"""

import logging
from pathlib import Path
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "warehouse.duckdb"


def load_to_warehouse(clean_df: pd.DataFrame, cancellations_df: pd.DataFrame) -> dict:
    con = duckdb.connect(str(DB_PATH))

    # --- Dimension: product ---
    dim_product = (
        clean_df[["stock_code", "description"]]
        .drop_duplicates(subset=["stock_code"], keep="first")
        .sort_values("stock_code")
    )

    # --- Dimension: country ---
    dim_country = pd.DataFrame({"country": sorted(clean_df["country"].unique())})
    dim_country["country_key"] = range(1, len(dim_country) + 1)

    # --- Dimension: date ---
    dim_date = pd.DataFrame({"invoice_date": sorted(clean_df["invoice_date"].dt.date.unique())})
    dim_date["date_key"] = pd.to_datetime(dim_date["invoice_date"])
    dim_date["year"] = dim_date["date_key"].dt.year
    dim_date["month"] = dim_date["date_key"].dt.month
    dim_date["month_name"] = dim_date["date_key"].dt.strftime("%B")
    dim_date["quarter"] = dim_date["date_key"].dt.quarter

    # --- Fact table: sales ---
    fact_sales = clean_df[[
        "invoice", "stock_code", "invoice_date", "quantity", "unit_price",
        "customer_id", "country", "gross_amount",
    ]].copy()
    fact_sales["invoice_date"] = fact_sales["invoice_date"].dt.date

    # --- Fact table: cancellations (kept separate, not netted against sales) ---
    fact_cancellations = cancellations_df[[
        "invoice", "stock_code", "invoice_date", "quantity", "unit_price", "customer_id", "country",
    ]].copy()
    fact_cancellations["invoice_date"] = fact_cancellations["invoice_date"].dt.date

    con.execute("CREATE OR REPLACE TABLE dim_product AS SELECT * FROM dim_product")
    con.execute("CREATE OR REPLACE TABLE dim_country AS SELECT * FROM dim_country")
    con.execute("CREATE OR REPLACE TABLE dim_date AS SELECT * FROM dim_date")
    con.execute("CREATE OR REPLACE TABLE fact_sales AS SELECT * FROM fact_sales")
    con.execute("CREATE OR REPLACE TABLE fact_cancellations AS SELECT * FROM fact_cancellations")

    row_counts = {
        "dim_product": con.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0],
        "dim_country": con.execute("SELECT COUNT(*) FROM dim_country").fetchone()[0],
        "dim_date": con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0],
        "fact_sales": con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0],
        "fact_cancellations": con.execute("SELECT COUNT(*) FROM fact_cancellations").fetchone()[0],
    }
    logger.info("Loaded warehouse tables: %s", row_counts)
    con.close()
    return row_counts