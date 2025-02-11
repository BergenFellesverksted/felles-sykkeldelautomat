import requests
import sqlite3
import time
from constants import *

# Constants
SYNC_INTERVAL = 60  # Sync every 60 seconds

def fetch_orders():
    """Fetch orders from the online API."""
    try:
        response = requests.get(f"{API_URL + "orders.php"}?api_key={API_KEY}")
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching orders: {e}")
        return []

def initialize_database():
    """Initialize the SQLite database with necessary tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            customer_name TEXT,
            order_date TEXT,
            order_total TEXT,
            pickup_code TEXT,
            pickup_time TEXT,
            return_code TEXT DEFAULT NULL,
            return_time TEXT DEFAULT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_id INTEGER,
            product_name TEXT,
            door TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
    """)

    conn.commit()
    conn.close()

def update_local_database(orders):
    """Update the local SQLite database with new/updated orders."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for order in orders:
        return_code = order.get("return_code", None)  # Default to None if missing
        return_time = order.get("return_time", None)  # Default to None if missing

        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, order_date, order_total, pickup_code, pickup_time, return_code, return_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET 
                customer_name = excluded.customer_name,
                order_date = excluded.order_date,
                order_total = excluded.order_total,
                pickup_code = excluded.pickup_code,
                pickup_time = excluded.pickup_time,
                return_code = COALESCE(excluded.return_code, orders.return_code),
                return_time = COALESCE(excluded.return_time, orders.return_time);
        """, [
            order["order_id"], order["customer_name"], order["order_date"], 
            order["order_total"], order["pickup_code"], order["pickup_time"], 
            return_code, return_time
        ])

        # Clear existing items for the order (to avoid duplicates)
        cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order["order_id"],))

        # Insert new items
        for item in order.get("items", []):
            cursor.execute("INSERT INTO order_items (order_id, product_name, door) VALUES (?, ?, ?)", (
                order["order_id"], item["product_name"], item["door"]
            ))

    conn.commit()
    conn.close()

def main():
    """Main loop to sync orders periodically."""
    initialize_database()
    while True:
        print("Fetching orders...")
        orders = fetch_orders()
        if orders:
            update_local_database(orders)
            print(f"Updated {len(orders)} orders.")
        else:
            print("No new orders found.")
        
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    main()
