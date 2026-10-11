-- Indexes and analytical views built on the raw tables (SQLite dialect).
CREATE INDEX idx_prod_cust ON products(customer_id);
CREATE INDEX idx_act_cust  ON monthly_activity(customer_id);

-- 12-month engagement per customer, incl. last-3 vs first-3 month trend
CREATE VIEW v_activity AS
SELECT customer_id,
       SUM(txn_count)                                   AS txns_12m,
       AVG(txn_count)                                   AS avg_monthly_txns,
       SUM(card_spend)                                  AS card_spend_12m,
       AVG(digital_logins)                              AS avg_logins,
       AVG(avg_balance)                                 AS avg_balance,
       AVG(credit_utilization)                          AS avg_utilization,
       AVG(CASE WHEN month >= '2026-06' THEN txn_count END)      AS txn_last3,
       AVG(CASE WHEN month <  '2025-12' THEN txn_count END)      AS txn_first3,
       AVG(CASE WHEN month >= '2026-06' THEN digital_logins END) AS login_last3,
       AVG(CASE WHEN month <  '2025-12' THEN digital_logins END) AS login_first3
FROM monthly_activity
GROUP BY customer_id;

-- Product holdings per customer
CREATE VIEW v_products AS
SELECT customer_id,
       COUNT(*)                                                              AS n_products,
       SUM(CASE WHEN product IN ('savings','current','fixed_deposit') THEN balance ELSE 0 END) AS deposit_balance,
       SUM(CASE WHEN product IN ('personal_loan','home_loan') THEN balance ELSE 0 END)         AS loan_balance,
       MAX(credit_limit)                                                     AS card_limit,
       SUM(annual_fee)                                                       AS fee_income,
       MAX(product = 'credit_card')   AS has_credit_card,
       MAX(product = 'personal_loan') AS has_personal_loan,
       MAX(product = 'home_loan')     AS has_home_loan,
       MAX(product = 'fixed_deposit') AS has_fixed_deposit,
       MAX(product = 'insurance')     AS has_insurance,
       MAX(product = 'current')       AS has_current
FROM products
GROUP BY customer_id;

-- Annual revenue, cost and profit per customer.
-- Assumptions: deposit margin 1.5%, loan spread 2.5%, card revolving margin 10% of limit*utilization,
-- interchange 1.2% of card spend, credit cost 1.2% of loans + 3% of revolving balance, servicing = fixed 3,000 + 8 per transaction + channel cost.
CREATE VIEW v_profitability AS
SELECT customer_id, nii_deposits, nii_loans, card_interest, interchange, fees,
       nii_deposits + nii_loans + card_interest + interchange + fees AS revenue,
       servicing_cost, credit_cost,
       servicing_cost + credit_cost AS cost,
       nii_deposits + nii_loans + card_interest + interchange + fees - servicing_cost - credit_cost AS profit
FROM (
  SELECT c.customer_id,
         p.deposit_balance * 0.015                                   AS nii_deposits,
         p.loan_balance * 0.025                                      AS nii_loans,
         COALESCE(p.card_limit * a.avg_utilization * 0.10, 0)        AS card_interest,
         a.card_spend_12m * 0.012                                    AS interchange,
         p.fee_income                                                AS fees,
         3000 + a.txns_12m * 8
             + CASE c.preferred_channel WHEN 'Branch' THEN 3000 WHEN 'Hybrid' THEN 1500 ELSE 400 END AS servicing_cost,
         p.loan_balance * 0.012 + COALESCE(p.card_limit * a.avg_utilization * 0.03, 0) AS credit_cost
  FROM customers c
  JOIN v_products p USING (customer_id)
  JOIN v_activity a USING (customer_id)
);
