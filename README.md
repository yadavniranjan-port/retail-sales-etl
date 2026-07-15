# Retail Sales ETL Pipeline

A Python ETL pipeline built against the real **UCI/Kaggle Online Retail II**
dataset (1,067,371 transaction rows, Dec 2009 - Dec 2011, UK-based online
retailer). Cleans and validates the data against an automated quality gate,
loads it into a star-schema warehouse, and produces a recurring sales report.

{

    data/raw/online_retail_ii.csv → extract.py → transform.py → quality_checks.py → load.py → DuckDB warehouse
│                                          │
invalid_rows.csv / cancellations.csv          generate_report.py → reports/

}

## What it does
1. **Extract** - reads the raw transaction export as-is.
2. **Transform** - standardises column names/types, removes exact duplicates,
   and splits every row into **three categories** rather than a simple
   clean/reject split:
   - **Clean** - genuine product sales
   - **Cancellations** - legitimate returns (`Invoice` starts with "C") -
     kept and logged separately, not merged into sales totals
   - **Invalid / non-merchandise** - postage charges, bank fees, manual
     adjustments, and rows with missing dates or non-positive prices -
     excluded from the sales fact table with a reason code
3. **Quality gate** - automated checks (excluded-rate threshold, null checks,
   value ranges) run before loading. Blocking checks halt the pipeline.
4. **Load** - star schema (`fact_sales`, `fact_cancellations`, `dim_product`,
   `dim_country`, `dim_date`) in a DuckDB warehouse file.
5. **Report** - monthly sales summary by country, top products, cancellation
   impact by month, and a sales trend chart.
6. **Monitoring** - every run logged to a `pipeline_runs` table (status, row
   counts, duration, error message).

## Why real data changed the design

Working with actual transactional data (rather than synthetic data) surfaced
a design decision synthetic data wouldn't have: **cancellations and
non-merchandise codes (postage, bank fees) aren't data errors** - they're
legitimate business records that would be wrong to either silently drop or
silently mix into sales figures. The three-way split (clean / cancellations /
invalid) reflects that, and is a stronger, more defensible design than a
simple pass/fail quarantine.

## Results from the real dataset (1,067,371 rows)

| Stage | Result |
|---|---|
| Rows extracted | 1,067,371 |
| Exact duplicates removed | 34,335 |
| Cancellations (kept separately) | 19,104 |
| Non-merchandise rows excluded (postage, fees, etc.) | 4,477 |
| Invalid rows excluded (bad date/price/etc.) | 6,019 |
| Clean sales rows loaded | 1,003,436 |
| Quality checks | 6/6 passed |
| Pipeline runtime | ~7 seconds |

Sales show a clear Christmas seasonality peak in November both years
(2010 and 2011) - a genuine pattern in the data, visible in
`reports/monthly_trend.png`.

## Project structure

{
retail-sales-etl/
├── src/
│   ├── extract.py                # extraction layer
│   ├── transform.py               # cleaning + three-way classification
│   ├── quality_checks.py          # automated quality gate
│   ├── load.py                    # star-schema load into DuckDB
│   ├── pipeline.py                # orchestrator + run logging
│   └── generate_report.py         # automated reporting
├── tests/
│   └── test_transform.py         # unit tests for transform + quality gate
├── data/
│   ├── raw/                      # source extract (gitignored)
│   └── processed/                # warehouse.duckdb, invalid_rows.csv, cancellations.csv (gitignored)
├── reports/                      # generated CSV reports + trend chart
├── requirements.txt
└── README.md

}


## Running it yourself

1. Download the dataset from Kaggle: https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci
2. Place the CSV at `data/raw/online_retail_ii.csv`
3. Then:

```bash
pip install -r requirements.txt
python src/pipeline.py            # extract -> transform -> quality gate -> load
python src/generate_report.py     # generate reports + trend chart
pytest tests/ -v                  # run test suite
```

## Design decisions worth calling out (useful for interview conversation)

- **Three-way classification, not pass/fail.** Cancellations and
  non-merchandise codes are real business events, not errors - conflating
  them with genuinely bad data would misrepresent the business.
- **Blocking vs. non-blocking checks.** A high excluded-rate or a null in a
  required field halts the pipeline; an unusually large single order
  (a real value of 80,995 units appears in this dataset) is logged as a
  warning for review, not treated as an automatic rejection.
- **DuckDB as a warehouse stand-in**, chosen so the pipeline runs fully
  offline with a genuine star-schema design - swappable for BigQuery or
  Snowflake by editing only `load.py`.
- **Run logging as a first-class citizen.** `pipeline_runs` answers "did
  last night's load succeed?" from SQL, not log files.

## Possible extensions

- Add `dbt` models on top of the DuckDB warehouse.
- Schedule with Airflow.
- Swap `load.py` for a real BigQuery/Snowflake connector.
- Build a Power BI dashboard reading directly from the warehouse.