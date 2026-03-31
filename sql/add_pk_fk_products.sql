-- ============================================================
-- Add Primary Keys to ecommerce_products
-- Run: psql -d ecommerce_products -f sql/add_pk_fk_products.sql
-- ============================================================

-- Step 1: Add Primary Keys
ALTER TABLE products
    ADD CONSTRAINT pk_products PRIMARY KEY (product_id);

ALTER TABLE sellers
    ADD CONSTRAINT pk_sellers PRIMARY KEY (seller_id);

-- order_items tidak punya single PK, pakai composite PK
ALTER TABLE order_items
    ADD CONSTRAINT pk_order_items PRIMARY KEY (order_id, order_item_id);

-- Step 2: Add Foreign Keys
ALTER TABLE order_items
    ADD CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id)
    REFERENCES products (product_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

ALTER TABLE order_items
    ADD CONSTRAINT fk_order_items_seller
    FOREIGN KEY (seller_id)
    REFERENCES sellers (seller_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- Verify
SELECT table_name, constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
  AND table_schema = 'public'
ORDER BY table_name, constraint_type;
