"""Generate a realistic synthetic retail-banking dataset (amounts in INR)."""
import numpy as np
import pandas as pd
from .config import RAW

N = 5000
MONTHS = [str(p) for p in pd.period_range("2025-09", "2026-08", freq="M")]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Nagpur", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur"]
FEES = {"savings": 0, "current": 600, "credit_card": 1200, "personal_loan": 2500,
        "home_loan": 8000, "fixed_deposit": 0, "insurance": 3000}


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def main(seed=42):
    rng = np.random.default_rng(seed)
    RAW.mkdir(parents=True, exist_ok=True)
    ids = np.array([f"C{i:05d}" for i in range(1, N + 1)])
    age = np.clip(rng.normal(40, 12, N), 21, 75).astype(int)
    income = np.round(np.exp(rng.normal(13.2, 0.55, N)), -3)
    z = (np.log(income) - 13.2) / 0.55
    tenure = rng.integers(3, 181, N)
    channel = rng.choice(["Digital", "Branch", "Hybrid"], N, p=[.45, .2, .35])
    complaints = rng.poisson(0.4, N)
    eng = rng.normal(0, 1, N) + (channel == "Digital") * 0.3 - complaints * 0.25

    held = {
        "savings": np.ones(N, bool),
        "current": rng.random(N) < sigmoid(z - 0.2) * 0.7,
        "credit_card": rng.random(N) < sigmoid(z + 0.2) * 0.8,
        "personal_loan": rng.random(N) < 0.25,
        "home_loan": rng.random(N) < np.where(age > 30, 0.2, 0.05),
        "fixed_deposit": rng.random(N) < sigmoid(z - 0.3) * 0.6,
        "insurance": rng.random(N) < 0.25,
    }
    mult = {"savings": (0.05, 0.6), "current": (0.02, 0.2), "fixed_deposit": (0.2, 1.2),
            "personal_loan": (0.1, 0.6), "home_loan": (1.5, 4.5), "insurance": (0.01, 0.04), "credit_card": (0.15, 0.4)}
    prod_rows = []
    for p, mask in held.items():
        lo, hi = mult[p]
        amt = np.round(income * rng.uniform(lo, hi, N), -2)
        for i in np.where(mask)[0]:
            prod_rows.append((ids[i], p, 0 if p == "credit_card" else amt[i],
                              amt[i] if p == "credit_card" else None, FEES[p]))
    products = pd.DataFrame(prod_rows, columns=["customer_id", "product", "balance", "credit_limit", "annual_fee"])
    n_prod = np.sum([m.astype(int) for m in held.values()], axis=0)

    base_txn = np.exp(2.6 + 0.4 * eng + 0.25 * z)[:, None]
    base_login = np.exp(1.9 + 0.5 * eng + 0.5 * (channel == "Digital"))[:, None]
    util_base = np.clip(rng.beta(2, 4, N) - 0.1 * z + 0.1 * complaints, 0.02, 0.98)[:, None]
    has_card = held["credit_card"]

    logit = (-1.8 - 0.85 * eng - 0.007 * (tenure - 60) - 0.35 * (n_prod - 3)
             + 1.3 * (has_card & (util_base[:, 0] > 0.6)) + 0.25 * complaints)
    churned = (rng.random(N) < sigmoid(logit)).astype(int)

    # Only ~45% of churners show a late-window engagement drop ("silent" churners give no warning),
    # and ~8% of loyal customers dip too (false alarms), so the signal is realistic, not perfect.
    shows = ((churned == 1) & (rng.random(N) < 0.45)) | ((churned == 0) & (rng.random(N) < 0.08))
    slope = rng.uniform(0.05, 0.15, N)
    decline = np.ones((N, 12))
    for k, m in enumerate(range(8, 12), start=1):
        decline[:, m] = np.where(shows, np.maximum(0.3, 1 - slope * k), 1.0)

    season = 1 + 0.08 * np.sin(np.arange(12) / 12 * 4 * np.pi)
    txn = rng.poisson(base_txn * season * decline)
    logins = rng.poisson(base_login * season * decline)
    spend = np.where(has_card[:, None], txn * 0.5 * rng.gamma(2, 700, (N, 12)), 0).round(-1)
    liquid = (products[products["product"].isin(["savings", "current"])]
              .groupby("customer_id")["balance"].sum().reindex(ids).fillna(0).to_numpy()[:, None])
    avg_bal = (liquid * (1 + rng.normal(0, 0.08, (N, 12))) * decline).round(-2)
    util = np.clip(util_base + rng.normal(0, 0.05, (N, 12)), 0, 1)
    util = np.where(has_card[:, None], util, np.nan).round(3)

    act = pd.DataFrame({
        "customer_id": np.repeat(ids, 12), "month": np.tile(MONTHS, N),
        "txn_count": txn.ravel(), "digital_logins": logins.ravel(), "card_spend": spend.ravel(),
        "avg_balance": avg_bal.ravel(), "credit_utilization": util.ravel()})
    cust = pd.DataFrame({
        "customer_id": ids, "age": age, "city": rng.choice(CITIES, N), "annual_income": income,
        "tenure_months": tenure, "preferred_channel": channel, "complaints_12m": complaints, "churned": churned})
    cust.to_csv(RAW / "customers.csv", index=False)
    products.to_csv(RAW / "products.csv", index=False)
    act.to_csv(RAW / "monthly_activity.csv", index=False)
    print(f"customers={len(cust)} products={len(products)} activity={len(act)} churn_rate={churned.mean():.1%}")


if __name__ == "__main__":
    main()
