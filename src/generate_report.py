"""
generate_report.py
------------------
Queries the warehouse and produces:
  - reports/monthly_sales_summary.csv   (country x month gross sales, units, orders)
  - reports/top_products.csv            (top 15 products by revenue)
  - reports/cancellation_summary.csv    (cancellation impact by month)
  - reports/monthly_trend.png           (chart: gross sales by month)
"""

import logging
from pathlib import Path
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from load import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("report")

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def generate_reports():
    con = duckdb.connect(str(DB_PATH))

    # Country x month summary
    summary = con.execute("""
        SELECT
            d.year,
            d.month_name,
            f.country,
            SUM(f.gross_amount) AS gross_sales,
            SUM(f.quantity) AS units_sold,
            COUNT(DISTINCT f.invoice) AS order_count,
            ROUND(SUM(f.gross_amount) / COUNT(DISTINCT f.invoice), 2) AS avg_order_value
        FROM fact_sales f
        JOIN dim_date d ON f.invoice_date = d.date_key
        GROUP BY d.year, d.month, d.month_name, f.country
        ORDER BY d.year, d.month, gross_sales DESC
    """).df()
    summary.to_csv(REPORTS_DIR / "monthly_sales_summary.csv", index=False)
    logger.info("Wrote monthly_sales_summary.csv (%s rows)", len(summary))

    # Top products
    top_products = con.execute("""
        SELECT
            p.description,
            SUM(f.gross_amount) AS gross_sales,
            SUM(f.quantity) AS units_sold
        FROM fact_sales f
        JOIN dim_product p ON f.stock_code = p.stock_code
        GROUP BY p.description
        ORDER BY gross_sales DESC
        LIMIT 15
    """).df()
    top_products.to_csv(REPORTS_DIR / "top_products.csv", index=False)
    logger.info("Wrote top_products.csv (%s rows)", len(top_products))

    # Cancellation impact by month
    cancellations = con.execute("""
        SELECT
            d.year, d.month_name,
            COUNT(DISTINCT c.invoice) AS cancelled_orders,
            SUM(ABS(c.quantity) * c.unit_price) AS cancelled_value
        FROM fact_cancellations c
        JOIN dim_date d ON c.invoice_date = d.date_key
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
    """).df()
    cancellations.to_csv(REPORTS_DIR / "cancellation_summary.csv", index=False)
    logger.info("Wrote cancellation_summary.csv (%s rows)", len(cancellations))

    # Monthly trend chart
    trend = con.execute("""
        SELECT d.year, d.month, d.month_name, SUM(f.gross_amount) AS gross_sales
        FROM fact_sales f
        JOIN dim_date d ON f.invoice_date = d.date_key
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
    """).df()
    trend["label"] = trend["month_name"].str[:3] + " " + trend["year"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(trend["label"], trend["gross_sales"], marker="o", color="#1A3557", linewidth=2)
    ax.set_title("Gross Sales by Month - Online Retail II", fontsize=14, fontweight="bold", color="#1A3557")
    ax.set_ylabel("Gross Sales (£)")
    ax.set_xlabel("Month")
    plt.xticks(rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "monthly_trend.png", dpi=150)
    plt.close(fig)
    logger.info("Wrote monthly_trend.png")

    con.close()


if __name__ == "__main__":
    generate_reports()