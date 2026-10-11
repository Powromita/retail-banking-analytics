import re
import sqlite3
from .config import DB, SQL_DIR


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def load_queries():
    text = (SQL_DIR / "02_queries.sql").read_text()
    parts = re.split(r"^-- name: (\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


QUERIES = load_queries()


def run(name):
    with connect() as con:
        return [dict(r) for r in con.execute(QUERIES[name]).fetchall()]
