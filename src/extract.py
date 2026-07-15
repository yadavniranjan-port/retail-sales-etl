"""
extract.py
----------
Extraction layer for the UCI/Kaggle Online Retail II dataset.
Reads the raw CSV export as-is - no cleaning here, that's transform.py's job.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def extract_transactions(filename: str = "online_retail_ii.csv") -> pd.DataFrame:
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Expected raw file not found: {path}")

    logger.info("Extracting raw transactions from %s", path)
    df = pd.read_csv(path, encoding="latin1", dtype={"Invoice": str, "StockCode": str})
    logger.info("Extracted %s rows, %s columns", *df.shape)
    return df