-- ============================================================
-- Setup: Create tables and insert sample data
-- Run: psql -f sql/setup_all.sql
-- ============================================================

-- ─── ecommerce_sales ─────────────────────────────────────────
\connect ecommerce_sales

CREATE TABLE IF NOT EXISTS customers (
    customer_id         TEXT PRIMARY KEY,
    customer_unique_id  TEXT,
    customer_name       TEXT,
    customer_email      TEXT,
    customer_city       TEXT,
    customer_state      TEXT,
    customer_zip_code   BIGINT,
    customer_created_at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id                       TEXT PRIMARY KEY,
    customer_id                    TEXT REFERENCES customers(customer_id),
    order_status                   TEXT,
    order_purchase_timestamp       TIMESTAMP,
    order_approved_at              TEXT,
    order_delivered_timestamp      TEXT,
    order_estimated_delivery_date  TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id           TEXT PRIMARY KEY,
    order_id             TEXT REFERENCES orders(order_id),
    payment_sequential   BIGINT,
    payment_type         TEXT,
    payment_installments BIGINT,
    payment_value        DOUBLE PRECISION
);

INSERT INTO customers VALUES
  ('c001','uc001','Budi Santoso','budi@email.com','Jakarta','DKI Jakarta',10110,'2023-01-10'),
  ('c002','uc002','Siti Rahayu','siti@email.com','Surabaya','Jawa Timur',60111,'2023-02-15'),
  ('c003','uc003','Ahmad Fauzi','ahmad@email.com','Bandung','Jawa Barat',40111,'2023-03-20'),
  ('c004','uc004','Dewi Kusuma','dewi@email.com','Medan','Sumatera Utara',20111,'2023-04-05'),
  ('c005','uc005','Rizky Pratama','rizky@email.com','Yogyakarta','DIY',55111,'2023-05-12'),
  ('c006','uc006','Rina Wati','rina@email.com','Semarang','Jawa Tengah',50111,'2023-06-18'),
  ('c007','uc007','Doni Setiawan','doni@email.com','Makassar','Sulawesi Selatan',90111,'2023-07-22'),
  ('c008','uc008','Maya Putri','maya@email.com','Palembang','Sumatera Selatan',30111,'2023-08-30'),
  ('c009','uc009','Hendra Wijaya','hendra@email.com','Balikpapan','Kalimantan Timur',76111,'2023-09-14'),
  ('c010','uc010','Lina Agustina','lina@email.com','Tangerang','Banten',15111,'2023-10-01')
ON CONFLICT DO NOTHING;

INSERT INTO orders VALUES
  ('o001','c001','delivered','2024-01-05 10:00:00','2024-01-05','2024-01-12','2024-01-15'),
  ('o002','c002','delivered','2024-01-10 11:30:00','2024-01-10','2024-01-17','2024-01-20'),
  ('o003','c003','delivered','2024-01-15 09:00:00','2024-01-15','2024-01-22','2024-01-25'),
  ('o004','c004','shipped','2024-02-01 14:00:00','2024-02-01',NULL,'2024-02-10'),
  ('o005','c005','delivered','2024-02-10 16:00:00','2024-02-10','2024-02-18','2024-02-20'),
  ('o006','c006','delivered','2024-02-20 08:00:00','2024-02-20','2024-02-27','2024-03-01'),
  ('o007','c007','canceled','2024-03-01 12:00:00',NULL,NULL,'2024-03-10'),
  ('o008','c008','delivered','2024-03-10 10:00:00','2024-03-10','2024-03-17','2024-03-20'),
  ('o009','c009','delivered','2024-03-20 15:00:00','2024-03-20','2024-03-27','2024-03-30'),
  ('o010','c010','processing','2024-04-01 09:00:00',NULL,NULL,'2024-04-10'),
  ('o011','c001','delivered','2024-04-05 11:00:00','2024-04-05','2024-04-12','2024-04-15'),
  ('o012','c002','delivered','2024-04-15 13:00:00','2024-04-15','2024-04-22','2024-04-25')
ON CONFLICT DO NOTHING;

INSERT INTO payments VALUES
  ('p001','o001',1,'credit_card',3,350000),
  ('p002','o002',1,'boleto',1,120000),
  ('p003','o003',1,'credit_card',6,890000),
  ('p004','o004',1,'debit_card',1,215000),
  ('p005','o005',1,'credit_card',2,560000),
  ('p006','o006',1,'voucher',1,75000),
  ('p007','o007',1,'credit_card',1,430000),
  ('p008','o008',1,'boleto',1,180000),
  ('p009','o009',1,'credit_card',4,720000),
  ('p010','o010',1,'debit_card',1,95000),
  ('p011','o011',1,'credit_card',2,410000),
  ('p012','o012',1,'credit_card',3,640000)
ON CONFLICT DO NOTHING;

-- ─── ecommerce_products ──────────────────────────────────────
\connect ecommerce_products

CREATE TABLE IF NOT EXISTS sellers (
    seller_id       TEXT PRIMARY KEY,
    seller_zip_code BIGINT,
    seller_city     TEXT,
    seller_state    TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id                  TEXT PRIMARY KEY,
    product_category_name       TEXT,
    product_name_length         BIGINT,
    product_description_length  BIGINT,
    product_photos_qty          BIGINT,
    product_weight_g            BIGINT,
    product_length_cm           BIGINT,
    product_height_cm           BIGINT,
    product_width_cm            BIGINT
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id             TEXT,
    order_item_id        BIGINT,
    product_id           TEXT REFERENCES products(product_id),
    seller_id            TEXT REFERENCES sellers(seller_id),
    shipping_limit_date  TEXT,
    price                DOUBLE PRECISION,
    freight_value        DOUBLE PRECISION,
    PRIMARY KEY (order_id, order_item_id)
);

INSERT INTO sellers VALUES
  ('s001',10110,'Jakarta','DKI Jakarta'),
  ('s002',60111,'Surabaya','Jawa Timur'),
  ('s003',40111,'Bandung','Jawa Barat'),
  ('s004',55111,'Yogyakarta','DIY'),
  ('s005',50111,'Semarang','Jawa Tengah')
ON CONFLICT DO NOTHING;

INSERT INTO products VALUES
  ('pr001','electronics',40,500,3,500,30,10,20),
  ('pr002','fashion',35,300,5,200,25,5,15),
  ('pr003','home_appliances',50,800,4,2000,60,40,50),
  ('pr004','books',20,200,1,300,20,3,15),
  ('pr005','sports',45,600,6,800,40,20,30),
  ('pr006','beauty',30,400,8,150,15,8,10),
  ('pr007','toys',25,350,4,600,35,25,25),
  ('pr008','food_beverage',15,100,2,1000,20,15,20)
ON CONFLICT DO NOTHING;

INSERT INTO order_items VALUES
  ('o001',1,'pr001','s001','2024-01-08',300000,50000),
  ('o002',1,'pr002','s002','2024-01-13',100000,20000),
  ('o003',1,'pr003','s003','2024-01-18',800000,90000),
  ('o004',1,'pr004','s001','2024-02-04',180000,35000),
  ('o005',1,'pr005','s004','2024-02-13',500000,60000),
  ('o006',1,'pr006','s005','2024-02-23',60000,15000),
  ('o007',1,'pr007','s002','2024-03-04',380000,50000),
  ('o008',1,'pr008','s003','2024-03-13',150000,30000),
  ('o009',1,'pr001','s001','2024-03-23',650000,70000),
  ('o010',1,'pr002','s004','2024-04-04',80000,15000),
  ('o011',1,'pr005','s005','2024-04-08',360000,50000),
  ('o012',1,'pr003','s002','2024-04-18',580000,60000)
ON CONFLICT DO NOTHING;

-- ─── ecommerce_analytics ─────────────────────────────────────
\connect ecommerce_analytics

CREATE TABLE IF NOT EXISTS customer_segments (
    customer_id       TEXT PRIMARY KEY,
    rfm_score         BIGINT,
    segment           TEXT,
    lifetime_value    DOUBLE PRECISION,
    total_orders      BIGINT,
    avg_order_value   DOUBLE PRECISION,
    last_purchase_date TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date               TEXT PRIMARY KEY,
    total_sales        BIGINT,
    total_orders       BIGINT,
    avg_order_value    BIGINT,
    new_customers      BIGINT,
    returning_customers BIGINT
);

INSERT INTO customer_segments VALUES
  ('c001',15,'champions',760000,2,380000,'2024-04-05','2024-04-06'),
  ('c002',14,'loyal',760000,2,380000,'2024-04-15','2024-04-16'),
  ('c003',12,'potential',890000,1,890000,'2024-01-15','2024-01-16'),
  ('c004',10,'at_risk',215000,1,215000,'2024-02-01','2024-02-02'),
  ('c005',13,'loyal',560000,1,560000,'2024-02-10','2024-02-11'),
  ('c006',9,'hibernating',75000,1,75000,'2024-02-20','2024-02-21'),
  ('c007',8,'lost',430000,1,430000,'2024-03-01','2024-03-02'),
  ('c008',11,'potential',180000,1,180000,'2024-03-10','2024-03-11'),
  ('c009',13,'loyal',720000,1,720000,'2024-03-20','2024-03-21'),
  ('c010',7,'new_customer',95000,1,95000,'2024-04-01','2024-04-02')
ON CONFLICT DO NOTHING;

INSERT INTO daily_metrics VALUES
  ('2024-01-05',350000,1,350000,1,0),
  ('2024-01-10',120000,1,120000,1,0),
  ('2024-01-15',890000,1,890000,1,0),
  ('2024-02-01',215000,1,215000,1,0),
  ('2024-02-10',560000,1,560000,1,0),
  ('2024-02-20',75000,1,75000,1,0),
  ('2024-03-01',430000,1,430000,1,0),
  ('2024-03-10',180000,1,180000,1,0),
  ('2024-03-20',720000,1,720000,1,0),
  ('2024-04-01',95000,1,95000,1,0),
  ('2024-04-05',410000,1,410000,0,1),
  ('2024-04-15',640000,1,640000,0,1)
ON CONFLICT DO NOTHING;
