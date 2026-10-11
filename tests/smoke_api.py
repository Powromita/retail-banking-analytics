from fastapi.testclient import TestClient
from src.api import app, QUERIES
c = TestClient(app)
for n in list(QUERIES)+["model"]:
    r = c.get(f"/api/{n}"); assert r.status_code == 200, (n, r.text)
    print(n, "ok", (len(r.json()) if isinstance(r.json(), list) else "obj"))
print(c.get("/api/kpis").json())
print(c.get("/").status_code, c.get("/reports/figures/roc_curve.png").status_code, c.get("/api/nope").status_code)
