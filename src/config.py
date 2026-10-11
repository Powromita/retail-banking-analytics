from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "bank.db"
SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
POWERBI = ROOT / "powerbi" / "data"
RISK_THRESHOLD = 0.30  # churn probability at/above which a customer is "at risk"
