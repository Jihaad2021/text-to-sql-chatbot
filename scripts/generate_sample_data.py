"""
Generate Sample E-commerce Data

Creates realistic sample data for 3 databases without needing Kaggle dataset.
"""

import pandas as pd
import random
from datetime import datetime, timedelta
from faker import Faker
import numpy as np

fake = Faker(['id_ID'])  # Indonesian locale
random.seed(42)
np.random.seed(42)

print("🏭 Generating sample e-commerce data...\n")

# ============================================================================
# DATABASE 1: SALES_DB
# ============================================================================

print("📊 Generating sales_db data...")

# 1. CUSTOMERS (100 customers)
print("  - customers table...")
customers_data = []
for i in range(1, 101):
    customers_data.append({
        'customer_id': f'CUST{i:04d}',
        'customer_unique_id': f'UUID{i:04d}',
        'customer_name': fake.name(),
        'customer_email': fake.email(),
        'customer_city': random.choice(['Jakarta', 'Bandung', 'Surabaya', 'Medan', 'Semarang']),
        'customer_state': random.choice(['DKI Jakarta', 'Jawa Barat', 'Jawa Timur', 'Sumatera Utara', 'Jawa Tengah']),
        'customer_zip_code': fake.postcode(),
        'customer_created_at': fake.date_between(start_date='-2y', end_date='-1y')
    })

customers_df = pd.DataFrame(customers_data)
print(f"    ✓ {len(customers_df)} customers generated")

# 2. ORDERS (500 orders - avg 5 orders per customer)
print("  - orders table...")
orders_data = []
order_id = 1

for _ in range(500):
    customer = random.choice(customers_data)
    order_date = fake.date_time_between(start_date='-6m', end_date='now')
    
    orders_data.append({
        'order_id': f'ORD{order_id:06d}',
        'customer_id': customer['customer_id'],
        'order_status': random.choice(['delivered', 'delivered', 'delivered', 'shipped', 'processing']),
        'order_purchase_timestamp': order_date,
        'order_approved_at': order_date + timedelta(hours=random.randint(1, 24)),
        'order_delivered_timestamp': order_date + timedelta(days=random.randint(3, 14)) if random.random() > 0.1 else None,
        'order_estimated_delivery_date': order_date + timedelta(days=random.randint(7, 21))
    })
    order_id += 1

orders_df = pd.DataFrame(orders_data)
print(f"    ✓ {len(orders_df)} orders generated")

# 3. PAYMENTS (1 payment per order)
print("  - payments table...")
payments_data = []

for order in orders_data:
    payment_value = round(random.uniform(50000, 5000000), 2)  # Rp 50K - 5M
    
    payments_data.append({
        'payment_id': f'PAY{order["order_id"][3:]}',
        'order_id': order['order_id'],
        'payment_sequential': 1,
        'payment_type': random.choice(['credit_card', 'credit_card', 'boleto', 'debit_card', 'voucher']),
        'payment_installments': random.choice([1, 1, 1, 3, 6, 12]),
        'payment_value': payment_value
    })

payments_df = pd.DataFrame(payments_data)
print(f"    ✓ {len(payments_df)} payments generated")

# ============================================================================
# DATABASE 2: PRODUCTS_DB
# ============================================================================

print("\n📦 Generating products_db data...")

# 4. PRODUCTS (50 products)
print("  - products table...")
categories = ['Electronics', 'Fashion', 'Home & Living', 'Beauty', 'Sports', 'Books', 'Toys']
products_data = []

for i in range(1, 51):
    category = random.choice(categories)
    products_data.append({
        'product_id': f'PROD{i:04d}',
        'product_category_name': category,
        'product_name_length': random.randint(20, 80),
        'product_description_length': random.randint(100, 500),
        'product_photos_qty': random.randint(1, 5),
        'product_weight_g': random.randint(100, 5000),
        'product_length_cm': random.randint(10, 100),
        'product_height_cm': random.randint(5, 50),
        'product_width_cm': random.randint(10, 80)
    })

products_df = pd.DataFrame(products_data)
print(f"    ✓ {len(products_df)} products generated")

# 5. SELLERS (20 sellers)
print("  - sellers table...")
sellers_data = []

for i in range(1, 21):
    sellers_data.append({
        'seller_id': f'SELL{i:04d}',
        'seller_zip_code': fake.postcode(),
        'seller_city': random.choice(['Jakarta', 'Bandung', 'Surabaya', 'Tangerang', 'Bekasi']),
        'seller_state': random.choice(['DKI Jakarta', 'Jawa Barat', 'Jawa Timur', 'Banten'])
    })

sellers_df = pd.DataFrame(sellers_data)
print(f"    ✓ {len(sellers_df)} sellers generated")

# 6. ORDER_ITEMS (500 items - 1 per order for simplicity)
print("  - order_items table...")
order_items_data = []

for i, order in enumerate(orders_data, 1):
    product = random.choice(products_data)
    seller = random.choice(sellers_data)
    price = round(random.uniform(50000, 5000000), 2)
    
    order_items_data.append({
        'order_id': order['order_id'],
        'order_item_id': i,
        'product_id': product['product_id'],
        'seller_id': seller['seller_id'],
        'shipping_limit_date': order['order_purchase_timestamp'] + timedelta(days=random.randint(5, 15)),
        'price': price,
        'freight_value': round(price * 0.1, 2)  # 10% of price
    })

order_items_df = pd.DataFrame(order_items_data)
print(f"    ✓ {len(order_items_df)} order items generated")

# ============================================================================
# DATABASE 3: ANALYTICS_DB
# ============================================================================

print("\n📈 Generating analytics_db data...")

# 7. CUSTOMER_SEGMENTS (derived from customers + orders)
print("  - customer_segments table...")
customer_segments_data = []

for customer in customers_data:
    customer_orders = [o for o in orders_data if o['customer_id'] == customer['customer_id']]
    total_spent = sum([p['payment_value'] for p in payments_data if p['order_id'] in [o['order_id'] for o in customer_orders]])
    
    # Segment based on spending
    if total_spent > 5000000:
        segment = 'VIP'
    elif total_spent > 2000000:
        segment = 'Regular'
    else:
        segment = 'Occasional'
    
    last_order = max([o['order_purchase_timestamp'] for o in customer_orders]) if customer_orders else customer['customer_created_at']
    
    customer_segments_data.append({
        'customer_id': customer['customer_id'],
        'rfm_score': random.randint(1, 5),
        'segment': segment,
        'lifetime_value': total_spent,
        'total_orders': len(customer_orders),
        'avg_order_value': total_spent / len(customer_orders) if customer_orders else 0,
        'last_purchase_date': last_order,
        'updated_at': datetime.now()
    })

customer_segments_df = pd.DataFrame(customer_segments_data)
print(f"    ✓ {len(customer_segments_df)} customer segments generated")

# 8. DAILY_METRICS (last 90 days)
print("  - daily_metrics table...")
daily_metrics_data = []
start_date = datetime.now() - timedelta(days=90)

for day_offset in range(90):
    date = start_date + timedelta(days=day_offset)
    day_orders = [o for o in orders_data if o['order_purchase_timestamp'].date() == date.date()]
    day_payments = [p for p in payments_data if p['order_id'] in [o['order_id'] for o in day_orders]]
    
    total_sales = sum([p['payment_value'] for p in day_payments])
    total_orders = len(day_orders)
    new_customers = len([c for c in customers_data if c['customer_created_at'] == date.date()])
    
    daily_metrics_data.append({
        'date': date.date(),
        'total_sales': total_sales,
        'total_orders': total_orders,
        'avg_order_value': total_sales / total_orders if total_orders > 0 else 0,
        'new_customers': new_customers,
        'returning_customers': total_orders - new_customers
    })

daily_metrics_df = pd.DataFrame(daily_metrics_data)
print(f"    ✓ {len(daily_metrics_df)} daily metrics generated")

# ============================================================================
# SAVE TO CSV
# ============================================================================

print("\n💾 Saving to CSV files...")

import os
os.makedirs('data/raw', exist_ok=True)

customers_df.to_csv('data/raw/customers.csv', index=False)
orders_df.to_csv('data/raw/orders.csv', index=False)
payments_df.to_csv('data/raw/payments.csv', index=False)
products_df.to_csv('data/raw/products.csv', index=False)
sellers_df.to_csv('data/raw/sellers.csv', index=False)
order_items_df.to_csv('data/raw/order_items.csv', index=False)
customer_segments_df.to_csv('data/raw/customer_segments.csv', index=False)
daily_metrics_df.to_csv('data/raw/daily_metrics.csv', index=False)

print(f"  ✓ All CSV files saved to data/raw/")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*60)
print("✅ SAMPLE DATA GENERATION COMPLETE!")
print("="*60)
print(f"\nGenerated files:")
print(f"  sales_db:")
print(f"    - customers.csv: {len(customers_df)} rows")
print(f"    - orders.csv: {len(orders_df)} rows")
print(f"    - payments.csv: {len(payments_df)} rows")
print(f"\n  products_db:")
print(f"    - products.csv: {len(products_df)} rows")
print(f"    - sellers.csv: {len(sellers_df)} rows")
print(f"    - order_items.csv: {len(order_items_df)} rows")
print(f"\n  analytics_db:")
print(f"    - customer_segments.csv: {len(customer_segments_df)} rows")
print(f"    - daily_metrics.csv: {len(daily_metrics_df)} rows")
print(f"\nTotal: ~{len(customers_df) + len(orders_df) + len(payments_df) + len(products_df) + len(sellers_df) + len(order_items_df) + len(customer_segments_df) + len(daily_metrics_df)} rows")
print(f"\n🎯 Next step: Run 'python scripts/setup_databases.py'")
