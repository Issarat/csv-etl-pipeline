# ER Diagram

[Back to README](../README.md)

The diagram reflects the PostgreSQL tables, keys, and relationships defined in
`sql/schma.sql`.

```mermaid
erDiagram
    customers ||--o{ orders : places
    orders ||--o{ order_items : contains

    customers {
        uuid customer_id PK
        uuid customer_unique_id
        varchar customer_zip_code_prefix
        text customer_city
        varchar customer_state
    }

    orders {
        uuid order_id PK
        uuid customer_id FK
        varchar order_status
        timestamp order_purchase_timestamp
        timestamp order_approved_at
        timestamp order_delivered_carrier_date
        timestamp order_delivered_customer_date
        timestamp order_estimated_delivery_date
    }

    order_items {
        uuid order_id PK, FK
        integer order_item_id PK
        uuid product_id
        uuid seller_id
        timestamp shipping_limit_date
        numeric price
        numeric freight_value
    }
```

## Keys and relationships

- `customers.customer_id` is the customer primary key.
- `orders.order_id` is the order primary key.
- `orders.customer_id` references `customers.customer_id`.
- `order_items` uses the composite primary key
  (`order_id`, `order_item_id`).
- `order_items.order_id` references `orders.order_id`.

## Required load order

The foreign keys require this load order:

1. `customers`
2. `orders`
3. `order_items`

`src/pipeline.py` must therefore define:

```python
DATA_LIST = ("customers", "orders", "order_items")
```
