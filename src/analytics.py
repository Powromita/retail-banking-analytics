"""Features, churn model + evaluation, CLV, segmentation, cross-sell, and Power BI exports."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import DB, FIGURES, POWERBI, REPORTS, RISK_THRESHOLD
from .db import connect

SEED = 42
FEATURES = ["age", "annual_income", "tenure_months", "complaints_12m", "n_products", "deposit_balance",
            "loan_balance", "avg_monthly_txns", "avg_logins", "avg_utilization", "has_credit_card",
            "txn_trend", "login_trend", "ch_digital", "ch_hybrid"]
ACTIONS = {
    "High-Value At-Risk": "Priority save: relationship manager call, fee waiver or rate review within 7 days",
    "Low-Value At-Risk": "Low-cost digital win-back: app nudges and a targeted offer",
    "High-Value Loyal": "Protect and reward: loyalty tier benefits and wealth/advisory offers",
    "Cross-Sell Targets": "Cross-sell next best product through preferred channel",
    "Stable Core": "Maintain: periodic engagement, monitor early-warning signals",
}


def load_frame():
    with connect() as con:
        df = pd.read_sql("""SELECT c.*, p.n_products, p.deposit_balance, p.loan_balance, p.has_credit_card,
                   p.has_personal_loan, p.has_home_loan, p.has_fixed_deposit, p.has_insurance,
                   a.avg_monthly_txns, a.avg_logins, a.avg_utilization, a.card_spend_12m,
                   (a.txn_last3 + 1) / (a.txn_first3 + 1) AS txn_trend,
                   (a.login_last3 + 1) / (a.login_first3 + 1) AS login_trend,
                   f.revenue, f.cost, f.profit
            FROM customers c JOIN v_products p USING (customer_id) JOIN v_activity a USING (customer_id)
            JOIN v_profitability f USING (customer_id)""", con)
    df["ch_digital"] = (df.preferred_channel == "Digital").astype(int)
    df["ch_hybrid"] = (df.preferred_channel == "Hybrid").astype(int)
    return df


def evaluate(y_true, proba, thr=0.5):
    pred = (proba >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred).ravel()
    return {"roc_auc": roc_auc_score(y_true, proba), "pr_auc": average_precision_score(y_true, proba),
            "precision": precision_score(y_true, pred), "recall": recall_score(y_true, pred),
            "f1": f1_score(y_true, pred), "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def train_and_score(df):
    X, y = df[FEATURES].fillna({"avg_utilization": 0}), df["churned"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=SEED)
    models = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "gradient_boosting": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=200, random_state=SEED),
    }
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    results = {}
    for name, m in models.items():
        m.fit(Xtr, ytr)
        proba = m.predict_proba(Xte)[:, 1]
        thr = float(np.clip(ytr.mean() * 1.6, 0.2, 0.5))  # operating threshold ~1.6x base rate
        results[name] = {**evaluate(yte, proba, thr), "threshold": round(thr, 3),
                         "cv_auc_mean": float(cross_val_score(models[name], X, y, cv=cv, scoring="roc_auc").mean())}
    best = max(results, key=lambda k: results[k]["roc_auc"])
    model = models[best]
    model.fit(Xtr, ytr)
    proba_te = model.predict_proba(Xte)[:, 1]
    imp = permutation_importance(model, Xte, yte, scoring="roc_auc", n_repeats=5, random_state=SEED)
    importance = sorted(zip(FEATURES, imp.importances_mean), key=lambda t: -t[1])
    # Decile lift on held-out data
    d = pd.DataFrame({"y": yte.values, "p": proba_te})
    d["decile"] = pd.qcut(d.p.rank(method="first", ascending=False), 10, labels=range(1, 11))
    lift = d.groupby("decile", observed=True).agg(customers=("y", "size"), churn_rate=("y", "mean")).reset_index()
    lift["lift"] = lift.churn_rate / yte.mean()
    # Out-of-fold probabilities so every customer gets an honest (not in-sample) score
    oof = cross_val_predict(models[best], X, y, cv=cv, method="predict_proba")[:, 1]
    fpr, tpr, _ = roc_curve(yte, proba_te)
    plot_figures(fpr, tpr, results[best]["roc_auc"], importance, lift)
    metrics = {"best_model": best, "test_size": int(len(yte)), "base_churn_rate": float(y.mean()),
               "models": results, "top_features": [{"feature": f, "importance": float(v)} for f, v in importance[:8]],
               "lift_by_decile": lift.assign(decile=lift.decile.astype(int)).round(3).to_dict("records")}
    return oof, metrics


def plot_figures(fpr, tpr, auc, importance, lift):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot(fpr, tpr, color="#0E6E6B", lw=2, label=f"AUC = {auc:.3f}")
    ax.plot([0, 1], [0, 1], color="#9AA5A8", ls="--", lw=1)
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title="Churn model ROC (held-out test)")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout(); fig.savefig(FIGURES / "roc_curve.png", dpi=150); plt.close(fig)
    top = importance[:8][::-1]
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    ax.barh([t[0] for t in top], [t[1] for t in top], color="#0E6E6B")
    ax.set(xlabel="Drop in AUC when shuffled", title="What drives churn")
    fig.tight_layout(); fig.savefig(FIGURES / "feature_importance.png", dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    ax.bar(lift.decile.astype(int), lift["lift"], color="#C9871F")
    ax.axhline(1, color="#9AA5A8", ls="--", lw=1)
    ax.set(xlabel="Risk decile (1 = highest predicted risk)", ylabel="Lift vs. average", title="Decile lift (held-out test)")
    fig.tight_layout(); fig.savefig(FIGURES / "decile_lift.png", dpi=150); plt.close(fig)


def add_business_layers(df, proba):
    df = df.copy()
    df["churn_prob"] = proba.round(4)
    df["is_at_risk"] = (df.churn_prob >= RISK_THRESHOLD).astype(int)
    df["risk_band"] = pd.cut(df.churn_prob, [-1, 0.15, RISK_THRESHOLD, 2], labels=["Low", "Medium", "High"]).astype(str)
    # 5-year CLV: annual profit discounted at 10%, survival from model-implied retention
    ret = 1 - df.churn_prob
    df["clv"] = sum(df.profit * ret ** t / 1.10 ** t for t in range(1, 6)).round(0)
    hi_value = df.profit >= df.profit.quantile(0.75)
    opp = pd.DataFrame({
        "home_loan": (df.has_home_loan == 0) & df.age.between(28, 45) & (df.annual_income >= 800_000),
        "personal_loan": (df.has_personal_loan == 0) & (df.tenure_months >= 24) & (df.annual_income >= 500_000) & (df.avg_utilization.fillna(0) < 0.5),
        "credit_card": (df.has_credit_card == 0) & (df.annual_income >= 400_000),
        "insurance": (df.has_insurance == 0) & ((df.has_home_loan == 1) | (df.has_personal_loan == 1)),
        "fixed_deposit": (df.has_fixed_deposit == 0) & (df.deposit_balance >= 0.4 * df.annual_income),
    })
    df["cross_sell_opportunities"] = opp.sum(axis=1)
    df["next_best_product"] = np.where(opp.any(axis=1), opp.idxmax(axis=1), "none")  # columns ordered by priority
    df["segment"] = np.select(
        [hi_value & (df.is_at_risk == 1), ~hi_value & (df.is_at_risk == 1), hi_value, df.cross_sell_opportunities >= 2],
        ["High-Value At-Risk", "Low-Value At-Risk", "High-Value Loyal", "Cross-Sell Targets"], "Stable Core")
    df["recommended_action"] = df.segment.map(ACTIONS)
    return df


def export(df):
    with connect() as con:
        df.to_sql("customer_scored", con, index=False, if_exists="replace")
    POWERBI.mkdir(parents=True, exist_ok=True)
    dim_cols = ["customer_id", "age", "city", "annual_income", "tenure_months", "preferred_channel", "complaints_12m",
                "churned", "n_products", "deposit_balance", "loan_balance", "avg_utilization", "revenue", "cost", "profit",
                "churn_prob", "is_at_risk", "risk_band", "clv", "segment", "cross_sell_opportunities",
                "next_best_product", "recommended_action"]
    out = df[dim_cols].copy()
    out["age_group"] = pd.cut(out.age, [0, 29, 39, 49, 59, 120], labels=["<30", "30-39", "40-49", "50-59", "60+"]).astype(str)
    out["tenure_band"] = pd.cut(out.tenure_months, [0, 11, 35, 83, 999], labels=["<1 yr", "1-3 yrs", "3-7 yrs", "7+ yrs"]).astype(str)
    out.round(4).to_csv(POWERBI / "dim_customer.csv", index=False)
    with connect() as con:
        pd.read_sql("SELECT * FROM monthly_activity", con).to_csv(POWERBI / "fact_monthly_activity.csv", index=False)
        pd.read_sql("SELECT * FROM products", con).to_csv(POWERBI / "fact_products.csv", index=False)
    months = pd.read_csv(POWERBI / "fact_monthly_activity.csv").month.unique()
    pd.DataFrame({"month": months, "month_start": [f"{m}-01" for m in months]}).to_csv(POWERBI / "dim_month.csv", index=False)


def main():
    df = load_frame()
    proba, metrics = train_and_score(df)
    df = add_business_layers(df, proba)
    export(df)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    b = metrics["models"][metrics["best_model"]]
    print(f"best model: {metrics['best_model']}  AUC={b['roc_auc']:.3f}  recall={b['recall']:.2f}  precision={b['precision']:.2f}")
    print(df.segment.value_counts().to_string())


if __name__ == "__main__":
    main()
