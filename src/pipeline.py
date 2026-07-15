"""
pipeline.py
-----------
Orchestrates extract -> transform -> quality checks -> load, and records
each run's outcome to a pipeline_runs log table in the warehouse.

Usage:
    python src/pipeline.py
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import extract_transactions
from transform import transform_transactions
from quality_checks import run_quality_checks, QualityCheckFailure
from load import load_to_warehouse, DB_PATH

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(REPORTS_DIR / "pipeline.log"),
    ],
)
logger = logging.getLogger("pipeline")


def log_run(status: str, stats: dict, duration_s: float, error: str = None):
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id INTEGER,
            run_timestamp TIMESTAMP,
            status VARCHAR,
            input_rows INTEGER,
            clean_rows INTEGER,
            cancellation_rows INTEGER,
            non_merchandise_rows INTEGER,
            invalid_rows INTEGER,
            duration_seconds DOUBLE,
            error_message VARCHAR
        )
    """)
    next_id = con.execute("SELECT COALESCE(MAX(run_id), 0) + 1 FROM pipeline_runs").fetchone()[0]
    con.execute(
        "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            next_id, datetime.now(), status,
            stats.get("input_rows"), stats.get("clean_rows"), stats.get("cancellation_rows"),
            stats.get("non_merchandise_rows"), stats.get("invalid_rows"),
            duration_s, error,
        ],
    )
    con.close()


def run_pipeline():
    start = time.time()
    stats = {}
    try:
        logger.info("=== Pipeline run started ===")

        raw_df = extract_transactions()

        result = transform_transactions(raw_df)
        stats = result["stats"]

        quality_results = run_quality_checks(result["clean"], stats)
        failed = [q for q in quality_results if not q["passed"]]
        if failed:
            logger.warning("%s non-blocking quality checks flagged", len(failed))

        row_counts = load_to_warehouse(result["clean"], result["cancellations"])

        duration = time.time() - start
        log_run("SUCCESS", stats, duration)

        logger.info("=== Pipeline run completed successfully in %.1fs ===", duration)
        logger.info("Warehouse row counts: %s", row_counts)
        return {"status": "SUCCESS", "stats": stats, "warehouse": row_counts, "quality_results": quality_results}

    except QualityCheckFailure as e:
        duration = time.time() - start
        log_run("FAILED_QUALITY_GATE", stats, duration, error=str(e))
        logger.error("Pipeline halted by quality gate: %s", e)
        raise
    except Exception as e:
        duration = time.time() - start
        log_run("FAILED", stats, duration, error=str(e))
        logger.exception("Pipeline failed with an unexpected error")
        raise


if __name__ == "__main__":
    run_pipeline()