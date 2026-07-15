"""
generate_charts.py
------------------
Additional stakeholder-facing charts, separate from generate_report.py so
the core (tested) reporting pipeline stays untouched. These are designed
to be glanced at in seconds, not analysed - clear titles, minimal clutter,
one clear takeaway per chart.

Outputs:
  - reports/top_products_chart.png
  - reports/top_countries_chart.png
  - reports/cancellation_rate_trend.png
"""

import logging
from pathlib import Path
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from load import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("charts")

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

NAVY = "#1A3557"
LIGHT_BLUE = "#5B7DB1"


def generate_charts():
    con = duckdb.connect(str(DB_PATH))

    # --- Chart 1: Top 10 products by revenue ---
    top_products = con.execute("""
        SELECT p.description, SUM(f.gross_amount) AS gross_sales
        FROM fact_sales f
        JOIN dim_product p ON f.stock_code = p.stock_code
        GROUP BY p.description
        ORDER BY gross_sales DESC
        LIMIT 10
    """).df()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top_products["description"][::-1], top_products["gross_sales"][::-1], color=NAVY)
    ax.set_title("Top 10 Products by Revenue", fontsize=14, fontweight="bold", color=NAVY)
    ax.set_xlabel("Gross Sales (£)")
    for i, v in enumerate(top_products["gross_sales"][::-1]):
        ax.text(v, i, f"  £{v:,.0f}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "top_products_chart.png", dpi=150)
    plt.close(fig)
    logger.info("Wrote top_products_chart.png")

    # --- Chart 2: Top 10 countries by revenue (UK excluded for scale, shown separately) ---
    top_countries = con.execute("""
        SELECT country, SUM(gross_amount) AS gross_sales, COUNT(DISTINCT invoice) AS orders
        FROM fact_sales
        GROUP BY country
        ORDER BY gross_sales DESC
        LIMIT 11
    """).df()

    uk_sales = top_countries[top_countries["country"] == "United Kingdom"]["gross_sales"].values
    uk_value = uk_sales[0] if len(uk_sales) else 0
    other_countries = top_countries[top_countries["country"] != "United Kingdom"].head(10)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1, 2]})

    axes[0].bar(["United Kingdom"], [uk_value], color=NAVY, width=0.5)
    axes[0].set_title("UK Sales\n(home market)", fontsize=12, fontweight="bold", color=NAVY)
    axes[0].set_ylabel("Gross Sales (£)")
    axes[0].text(0, uk_value, f"£{uk_value:,.0f}", ha="center", va="bottom", fontsize=10)

    axes[1].barh(other_countries["country"][::-1], other_countries["gross_sales"][::-1], color=LIGHT_BLUE)
    axes[1].set_title("Top 10 International Markets\n(excluding UK, for scale)", fontsize=12, fontweight="bold", color=NAVY)
    axes[1].set_xlabel("Gross Sales (£)")
    for i, v in enumerate(other_countries["gross_sales"][::-1]):
        axes[1].text(v, i, f"  £{v:,.0f}", va="center", fontsize=8)

    fig.suptitle("Sales by Market: UK vs. International", fontsize=14, fontweight="bold", color=NAVY)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "top_countries_chart.png", dpi=150)
    plt.close(fig)
    logger.info("Wrote top_countries_chart.png")

    # --- Chart 3: Cancellation rate trend (% of orders cancelled, by month) ---
    monthly_orders = con.execute("""
        SELECT d.year, d.month, d.month_name, COUNT(DISTINCT f.invoice) AS total_orders
        FROM fact_sales f
        JOIN dim_date d ON f.invoice_date = d.date_key
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
    """).df()

    monthly_cancellations = con.execute("""
        SELECT d.year, d.month, COUNT(DISTINCT c.invoice) AS cancelled_orders
        FROM fact_cancellations c
        JOIN dim_date d ON c.invoice_date = d.date_key
        GROUP BY d.year, d.month
        ORDER BY d.year, d.month
    """).df()

    merged = monthly_orders.merge(monthly_cancellations, on=["year", "month"], how="left")
    merged["cancelled_orders"] = merged["cancelled_orders"].fillna(0)
    merged["cancellation_rate_pct"] = (
        merged["cancelled_orders"] / (merged["total_orders"] + merged["cancelled_orders"]) * 100
    ).round(2)
    merged["label"] = merged["month_name"].str[:3] + " " + merged["year"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(merged["label"], merged["cancellation_rate_pct"], marker="o", color="#C0392B", linewidth=2)
    ax.axhline(merged["cancellation_rate_pct"].mean(), linestyle="--", color="gray", linewidth=1,
               label=f"Average: {merged['cancellation_rate_pct'].mean():.1f}%")
    ax.set_title("Order Cancellation Rate by Month", fontsize=14, fontweight="bold", color=NAVY)
    ax.set_ylabel("Cancellation Rate (%)")
    ax.set_xlabel("Month")
    ax.legend()
    plt.xticks(rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "cancellation_rate_trend.png", dpi=150)
    plt.close(fig)
    logger.info("Wrote cancellation_rate_trend.png")

    con.close()


if __name__ == "__main__":
    generate_charts()