"""FastAPI backend: serves analytics from SQLite and the static dashboard."""
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import REPORTS, ROOT
from .db import QUERIES, run

app = FastAPI(title="Retail Banking Customer Analytics API")


@app.get("/api/model")
def model():
    path = REPORTS / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "Run `python run_pipeline.py` first")
    return json.loads(path.read_text())


@app.get("/api/{name}")
def query(name: str):
    if name not in QUERIES:
        raise HTTPException(404, f"Unknown query '{name}'. Available: {sorted(QUERIES)}")
    rows = run(name)
    return rows[0] if name == "kpis" else rows


app.mount("/reports", StaticFiles(directory=REPORTS), name="reports")


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")
