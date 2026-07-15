"""
test_transform.py
------------------
Unit tests for transform.py and quality_checks.py, using small hand-built
DataFrames so tests run in milliseconds instead of loading the full 1M-row
file. Run with: pytest tests/ -v
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transform import transform_transactions
from quality_checks import run_quality_checks, QualityCheckFailure


def make_sample_df():
    return pd.DataFrame([
        # normal valid sale
        {"Invoice": "500001", "StockCode": "10001", "Description": "Wooden Star",
         "Quantity": 5, "InvoiceDate": "2011-01-05 10:00:00", "Price": 2.5,
         "Customer ID": 17850, "Country": "United Kingdom"},
        # exact duplicate of the row above
        {"Invoice": "500001", "StockCode": "10001", "Description": "Wooden Star",
         "Quantity": 5, "InvoiceDate": "2011-01-05 10:00:00", "Price": 2.5,
         "Customer ID": 17850, "Country": "United Kingdom"},
        # cancellation - legitimate, not invalid
        {"Invoice": "C500002", "StockCode": "10002", "Description": "Glass Bauble",
         "Quantity": -2, "InvoiceDate": "2011-01-06 11:00:00", "Price": 4.0,
         "Customer ID": 17851, "Country": "United Kingdom"},
        # non-merchandise code (postage)
        {"Invoice": "500003", "StockCode": "POST", "Description": "Postage",
         "Quantity": 1, "InvoiceDate": "2011-01-07 09:00:00", "Price": 18.0,
         "Customer ID": 17852, "Country": "France"},
        # invalid: zero price
        {"Invoice": "500004", "StockCode": "10003", "Description": "Tin Sign",
         "Quantity": 3, "InvoiceDate": "2011-01-08 12:00:00", "Price": 0,
         "Customer ID": 17853, "Country": "Germany"},
    ])


def test_deduplication_removes_exact_duplicate():
    result = transform_transactions(make_sample_df())
    assert result["stats"]["exact_duplicates_removed"] == 1


def test_cancellation_kept_separate_not_invalid():
    result = transform_transactions(make_sample_df())
    assert "C500002" in set(result["cancellations"]["invoice"])
    assert "C500002" not in set(result["clean"]["invoice"])
    assert "C500002" not in set(result["invalid"]["invoice"])


def test_non_merchandise_excluded_from_clean():
    result = transform_transactions(make_sample_df())
    assert "500003" not in set(result["clean"]["invoice"])


def test_zero_price_flagged_invalid():
    result = transform_transactions(make_sample_df())
    assert "500004" in set(result["invalid"]["invoice"])
    reason = result["invalid"].set_index("invoice").loc["500004", "_invalid_reason"]
    assert reason == "non_positive_price"


def test_clean_set_contains_only_genuine_sale():
    result = transform_transactions(make_sample_df())
    assert set(result["clean"]["invoice"]) == {"500001"}


def test_gross_amount_calculated_correctly():
    result = transform_transactions(make_sample_df())
    row = result["clean"][result["clean"]["invoice"] == "500001"].iloc[0]
    assert row["gross_amount"] == pytest.approx(12.5)  # 5 * 2.5


def test_quality_gate_flags_row_level_checks_correctly():
    # This tiny sample deliberately has a 40% excluded rate, which correctly
    # trips the rate-threshold gate - that's expected behaviour, not a bug.
    # Here we isolate the row-level checks (nulls, positive values) to
    # confirm they pass cleanly on the clean subset itself.
    
    result = transform_transactions(make_sample_df())
    healthy_stats = {**result["stats"], "invalid_rows": 0, "non_merchandise_rows": 0}
    results = run_quality_checks(result["clean"], healthy_stats)
    row_level_checks = [r for r in results if r["check"] != "excluded_rate_below_threshold"]
    assert all(r["passed"] for r in row_level_checks if r["blocking"])


def test_quality_gate_blocks_when_excluded_rate_too_high():
    result = transform_transactions(make_sample_df())
    with pytest.raises(QualityCheckFailure):
        run_quality_checks(result["clean"], result["stats"])