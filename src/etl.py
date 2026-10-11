"""Load raw CSVs into SQLite and create the analytical views."""
import pandas as pd
import sqlite3
from .config import DB, RAW, SQL_DIR


def main():
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    for t in ["customers", "products", "monthly_activity"]:
        pd.read_csv(RAW / f"{t}.csv").to_sql(t, con, index=False)
    con.executescript((SQL_DIR / "01_views.sql").read_text())
    con.commit()
    n = con.execute("SELECT COUNT(*), ROUND(SUM(profit)) FROM v_profitability").fetchone()
    print(f"loaded {DB.name}: {n[0]} customers, total profit INR {n[1]:,.0f}")
    con.close()


if __name__ == "__main__":
    main()
