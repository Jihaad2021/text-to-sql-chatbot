-- ============================================================
-- Add Primary Keys to ecommerce_sales
-- Run: psql -d ecommerce_sales -f sql/add_pk_fk_sales.sql
-- ============================================================

-- Step 1: Add Primary Keys
ALTER TABLE customers
    ADD CONSTRAINT pk_customers PRIMARY KEY (customer_id);

ALTER TABLE orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (order_id);

ALTER TABLE payments
    ADD CONSTRAINT pk_payments PRIMARY KEY (payment_id);

-- Step 2: Add Foreign Keys
ALTER TABLE orders
    ADD CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers (customer_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

ALTER TABLE payments
    ADD CONSTRAINT fk_payments_order
    FOREIGN KEY (order_id)
    REFERENCES orders (order_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- Verify PKs
SELECT table_name, constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
  AND table_schema = 'public'
ORDER BY table_name, constraint_type;
