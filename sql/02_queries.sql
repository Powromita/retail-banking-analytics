-- Named analytical queries over the scored table. Used by the API and runnable in any SQLite client.

-- name: kpis
SELECT COUNT(*)                                              AS customers,
       ROUND(AVG(churned) * 100, 1)                          AS churn_rate_pct,
       ROUND(SUM(revenue))                                   AS revenue,
       ROUND(SUM(profit))                                    AS profit,
       ROUND(SUM(profit) * 100.0 / SUM(revenue), 1)          AS margin_pct,
       ROUND(AVG(clv))                                       AS avg_clv,
       ROUND(AVG(avg_utilization) * 100, 1)                  AS avg_utilization_pct,
       ROUND(AVG(n_products), 2)                             AS avg_products,
       SUM(is_at_risk)                                       AS at_risk_customers,
       ROUND(SUM(CASE WHEN is_at_risk = 1 THEN profit END))  AS profit_at_risk,
       ROUND(SUM(CASE WHEN is_at_risk = 1 THEN profit END) * 100.0 / SUM(profit), 1) AS profit_at_risk_pct,
       ROUND(AVG(CASE WHEN preferred_channel IN ('Digital','Hybrid') THEN 1.0 ELSE 0 END) * 100, 1) AS digital_adoption_pct
FROM customer_scored;

-- name: segments
SELECT segment, COUNT(*) AS customers, ROUND(SUM(revenue)) AS revenue, ROUND(SUM(profit)) AS profit,
       ROUND(AVG(clv)) AS avg_clv, ROUND(AVG(churn_prob) * 100, 1) AS avg_churn_prob_pct,
       ROUND(AVG(churned) * 100, 1) AS churn_rate_pct
FROM customer_scored GROUP BY segment ORDER BY profit DESC;

-- name: churn_by_utilization
SELECT CASE WHEN avg_utilization IS NULL THEN 'No card'
            WHEN avg_utilization < 0.3 THEN '< 30%'
            WHEN avg_utilization < 0.6 THEN '30-60%'
            WHEN avg_utilization < 0.8 THEN '60-80%' ELSE '> 80%' END AS band,
       COUNT(*) AS customers, ROUND(AVG(churned) * 100, 1) AS churn_rate_pct
FROM customer_scored GROUP BY band
ORDER BY CASE band WHEN 'No card' THEN 0 WHEN '< 30%' THEN 1 WHEN '30-60%' THEN 2 WHEN '60-80%' THEN 3 ELSE 4 END;

-- name: churn_by_tenure
SELECT CASE WHEN tenure_months < 12 THEN '< 1 yr' WHEN tenure_months < 36 THEN '1-3 yrs'
            WHEN tenure_months < 84 THEN '3-7 yrs' ELSE '7+ yrs' END AS bucket,
       COUNT(*) AS customers, ROUND(AVG(churned) * 100, 1) AS churn_rate_pct
FROM customer_scored GROUP BY bucket
ORDER BY MIN(tenure_months);

-- name: product_mix
SELECT p.product, COUNT(*) AS holders,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM customers), 1) AS penetration_pct,
       ROUND(AVG(s.churned) * 100, 1) AS holder_churn_pct
FROM products p JOIN customer_scored s USING (customer_id)
GROUP BY p.product ORDER BY holders DESC;

-- name: monthly_trend
SELECT month, SUM(txn_count) AS txns, ROUND(SUM(card_spend)) AS card_spend, ROUND(AVG(digital_logins), 1) AS avg_logins
FROM monthly_activity GROUP BY month ORDER BY month;

-- name: cross_sell
SELECT next_best_product AS product, COUNT(*) AS customers, ROUND(SUM(profit)) AS current_profit
FROM customer_scored WHERE next_best_product <> 'none' AND is_at_risk = 0
GROUP BY next_best_product ORDER BY customers DESC;

-- name: top_at_risk
SELECT customer_id, city, segment, ROUND(churn_prob * 100, 1) AS churn_prob_pct, ROUND(profit) AS annual_profit,
       ROUND(clv) AS clv, next_best_product, recommended_action
FROM customer_scored WHERE is_at_risk = 1 ORDER BY clv DESC LIMIT 15;
