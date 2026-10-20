-- PostgreSQL schema for the three clean Olist CSV datasets.
-- Existing 32-character hexadecimal IDs load directly into PostgreSQL UUID columns.
-- Load in dependency order: customers, orders, order_items.

CREATE TABLE IF NOT EXISTS customers (
    customer_id UUID PRIMARY KEY,
    customer_unique_id UUID NOT NULL,
    customer_zip_code_prefix VARCHAR(5) NOT NULL,
    customer_city TEXT NOT NULL,
    customer_state VARCHAR(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customers (customer_id),
    order_status VARCHAR(20) NOT NULL CHECK (
        order_status IN (
            'created', 'approved', 'invoiced', 'processing',
            'shipped', 'delivered', 'canceled', 'unavailable'
        )
    ),
    order_purchase_timestamp TIMESTAMP NOT NULL,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id UUID NOT NULL REFERENCES orders (order_id),
    order_item_id INTEGER NOT NULL CHECK (order_item_id > 0),
    product_id UUID NOT NULL,
    seller_id UUID NOT NULL,
    shipping_limit_date TIMESTAMP NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    freight_value NUMERIC(12, 2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id
    ON orders (customer_id);

CREATE INDEX IF NOT EXISTS idx_customers_unique_id
    ON customers (customer_unique_id);
