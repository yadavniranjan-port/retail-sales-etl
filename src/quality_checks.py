"""
quality_checks.py
------------------
Automated data quality gate, adapted for the real Online Retail II dataset.
Runs after transform and before load. Blocking checks halt the pipeline;
non-blocking checks are logged as warnings but don't stop the run.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


class QualityCheckFailure(Exception):
    pass


def run_quality_checks(clean_df: pd.DataFrame, stats: dict) -> list:
    results = []

    def check(name, condition, message, blocking=True):
        passed = bool(condition)
        results.append({"check": name, "passed": passed, "message": message, "blocking": blocking})
        level = logging.INFO if passed else logging.ERROR
        logger.log(level, "[%s] %s - %s", name, "PASS" if passed else "FAIL", message)
        return passed

    # 1. Combined invalid + non-merchandise rate shouldn't be excessive
    excluded = stats["invalid_rows"] + stats["non_merchandise_rows"]
    excluded_rate = excluded / max(stats["input_rows"], 1)
    check(
        "excluded_rate_below_threshold",
        excluded_rate < 0.03,
        f"Excluded (invalid + non-merchandise) rate {excluded_rate:.2%} (threshold 3%)",
    )

    # 2. No nulls in required fields for the clean set
    required_cols = ["invoice", "stock_code", "invoice_date", "quantity", "unit_price"]
    nulls = clean_df[required_cols].isna().sum().sum()
    check("no_nulls_in_required_fields", nulls == 0, f"{nulls} nulls found across required columns")

    # 3. Value ranges - clean set should only contain genuine positive sales
    check(
        "quantity_positive_in_clean_set",
        (clean_df["quantity"] > 0).all(),
        "All quantities are positive in the clean set (cancellations handled separately)",
    )
    check(
        "unit_price_positive_in_clean_set",
        (clean_df["unit_price"] > 0).all(),
        "All unit prices are positive in the clean set",
    )

    # 4. No unreasonably large single-line orders (sanity check, non-blocking)
    max_qty = clean_df["quantity"].max()
    check(
        "no_extreme_quantity_outliers",
        max_qty < 100000,
        f"Max quantity in clean set: {max_qty}",
        blocking=False,
    )

    # 5. Date range sanity
    max_date = clean_df["invoice_date"].max()
    check(
        "no_future_dates",
        max_date <= pd.Timestamp.today(),
        f"Max invoice_date is {max_date.date()}",
        blocking=False,
    )

    blocking_failures = [r for r in results if r["blocking"] and not r["passed"]]
    if blocking_failures:
        names = ", ".join(r["check"] for r in blocking_failures)
        raise QualityCheckFailure(f"Blocking quality checks failed: {names}")

    return results