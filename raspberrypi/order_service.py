import time
import requests
import sqlite3
import serial
import threading
import subprocess
import os
import cv2
import numpy as np
from datetime import datetime, timedelta
from pyzbar.pyzbar import decode
from RPi import GPIO
from RPLCD.i2c import CharLCD
from constants import *  # Make sure DB_FILE, API_URL, API_KEY, OPEN_ALL_CODE, ALL_DOORS, etc. are defined here

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
SERIAL_PORT = "/dev/ttyUSB0"
DELAY_BETWEEN_GROUPS = 0.5
OFFLINE_SYNC_INTERVAL = 300   # 5 minutes for syncing offline actions
ORDERS_SYNC_INTERVAL = 60     # Sync orders every 60 seconds
LCD_TIMEOUT = 20              # Time before the LCD screen turns off without input
MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP = 15  # Minutes to allow pickup after pickup time

# Keypad Configuration
KEYPAD = [
    [1, 2, 3, 'A'],
    [4, 5, 6, 'B'],
    [7, 8, 9, 'C'],
    ['*', 0, '#', 'D']
]
ROW_PINS = [12, 16, 20, 21]
COL_PINS = [25, 8, 7, 1]

# ------------------------------------------------------------------------------
# LCD and GPIO Setup
# ------------------------------------------------------------------------------
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
lcd.backlight_enabled = False

GPIO.setmode(GPIO.BCM)
GPIO.setup(ROW_PINS, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(COL_PINS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# ------------------------------------------------------------------------------
# Database Initialization
# ------------------------------------------------------------------------------
def initialize_database():
    """Creates the necessary tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Updated orders table: no longer storing return_code/return_time,
    # but storing opening_code, start_time, and end_time.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            customer_name TEXT,
            order_date TEXT,
            order_total TEXT,
            pickup_code TEXT,
            pickup_time TEXT,
            opening_code TEXT DEFAULT NULL,
            start_time TEXT DEFAULT NULL,
            end_time TEXT DEFAULT NULL
        );
    """)

    # Table for order items associated with each order
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_id INTEGER,
            product_name TEXT,
            door TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
    """)

    # Table for storing actions that have not yet been synced with the API
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offline_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            action TEXT CHECK(action IN ('pickup', 'opening')),
            action_time TEXT DEFAULT (datetime('now')),
            synced INTEGER DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()

# ------------------------------------------------------------------------------
# Orders Sync Functions (runs in its own thread)
# ------------------------------------------------------------------------------
def fetch_orders():
    """Fetch orders from the online API."""
    try:
        response = requests.get(f"{API_URL}orders.php?api_key={API_KEY}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching orders: {e}")
        return []

def sanitize_value(value):
    """Convert lists to comma-separated strings; otherwise return the value unchanged."""
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return value

def update_local_database(orders):
    """Update the local SQLite database with new/updated orders."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for order in orders:
        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, order_date, order_total, pickup_code, pickup_time, opening_code, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET 
                customer_name = excluded.customer_name,
                order_date = excluded.order_date,
                order_total = excluded.order_total,
                pickup_code = excluded.pickup_code,
                pickup_time = excluded.pickup_time,
                opening_code = COALESCE(excluded.opening_code, orders.opening_code),
                start_time = COALESCE(excluded.start_time, orders.start_time),
                end_time = COALESCE(excluded.end_time, orders.end_time);
        """, [
            order["order_id"],
            order["customer_name"],
            order["order_date"],
            order["order_total"],
            order["pickup_code"],
            order["pickup_time"],
            sanitize_value(order.get("opening_code", None)),
            sanitize_value(order.get("start_time", None)),
            sanitize_value(order.get("end_time", None))
        ])

        # Remove existing items to avoid duplicates
        cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order["order_id"],))

        # Insert order items if available
        for item in order.get("items", []):
            cursor.execute("INSERT INTO order_items (order_id, product_name, door) VALUES (?, ?, ?)", (
                order["order_id"], item["product_name"], item["door"]
            ))

    conn.commit()
    conn.close()

def fetch_orders_now():
    print("Fetching orders...")
    orders = fetch_orders()
    if orders:
        update_local_database(orders)
        print(f"Updated {len(orders)} orders.")
    else:
        print("No new orders found.")

def orders_sync_loop():
    """Loop that periodically syncs orders from the API."""
    while True:
        fetch_orders_now()
        time.sleep(ORDERS_SYNC_INTERVAL)

# ------------------------------------------------------------------------------
# Offline Actions Sync (runs in its own thread)
# ------------------------------------------------------------------------------
def sync_offline_actions():
    """Attempts to sync offline actions with the API, including action_time."""
    print("Checking offline pickups")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, order_id, action, action_time FROM offline_actions WHERE synced = 0")
    unsynced_actions = cursor.fetchall()

    for action_id, order_id, action, action_time in unsynced_actions:
        if send_order_update(order_id, action, action_time, store_on_fail=False):
            cursor.execute("UPDATE offline_actions SET synced = 1 WHERE id = ?", (action_id,))
    
    conn.commit()
    conn.close()

def offline_sync_loop():
    """Loop that periodically attempts to sync offline actions."""
    while True:
        sync_offline_actions()
        time.sleep(OFFLINE_SYNC_INTERVAL)

# ------------------------------------------------------------------------------
# Other Functions (Keypad, QR scanning, relay control, etc.)
# ------------------------------------------------------------------------------
def read_keypad():
    """Scans the keypad and returns the pressed key."""
    for row_num, row_pin in enumerate(ROW_PINS):
        GPIO.output(row_pin, GPIO.HIGH)
        for col_num, col_pin in enumerate(COL_PINS):
            if GPIO.input(col_pin) == GPIO.HIGH:
                GPIO.output(row_pin, GPIO.LOW)
                return KEYPAD[row_num][col_num]
        GPIO.output(row_pin, GPIO.LOW)
    return None

def fetch_order_by_code(code):
    """
    Fetches an order by its code.

    For a pickup code:
      - If the order has not been picked up, it is valid.
      - If the order was picked up, the code remains valid if within MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP minutes of the pickup time.
      - Otherwise, returns (order_id, 'already_picked_up').

    For an opening code:
      - It is valid only if the current time is between start_time and end_time.
      - Otherwise, returns (order_id, 'not_in_opening_window').
    
    Also, if there is a recent unsynced offline action (within 15 minutes), the order is blocked.
    If no order is found, returns (None, None).
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT order_id, pickup_code, pickup_time, opening_code, start_time, end_time
        FROM orders
        WHERE pickup_code = ? OR opening_code = ?
    """, (code, code))
    order = cursor.fetchone()
    if order is None:
        conn.close()
        return (None, None)
    
    order_id, pickup_code, pickup_time, opening_code, start_time, end_time = order

    # Check for recent unsynced offline actions (blocking further processing)
    earliest_accepted_time = datetime.now() - timedelta(minutes=MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP)
    cursor.execute("""
        SELECT id FROM offline_actions
        WHERE order_id = ? AND synced = 0 AND datetime(action_time) > ?
    """, (order_id, earliest_accepted_time.isoformat(' ')))
    offline_action = cursor.fetchone()
    if offline_action:
        conn.close()
        return (None, None)

    action = None
    if code == pickup_code:
        # For a pickup code.
        if pickup_time in (None, 'Not Picked Up'):
            action = 'pickup'
        else:
            try:
                pickup_dt = datetime.fromisoformat(pickup_time)
            except Exception:
                conn.close()
                return (None, None)
            if datetime.now() <= pickup_dt + timedelta(minutes=MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP):
                action = 'pickup'
            else:
                conn.close()
                return (order_id, 'already_picked_up')
    elif code == opening_code:
        # For an opening code, ensure that start_time and end_time are configured.
        if start_time in (None, 'Not Started') or end_time in (None, 'Not Ended'):
            conn.close()
            return (order_id, 'opening_not_configured')
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        except Exception:
            conn.close()
            return (None, None)
        if start_dt <= datetime.now() <= end_dt:
            action = 'opening'
        else:
            conn.close()
            return (order_id, 'not_in_opening_window')
    else:
        conn.close()
        return (None, None)

    conn.close()
    return (order_id, action)

def fetch_door_items(order_id):
    """Fetches doors associated with items in an order."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT door FROM order_items WHERE order_id = ?", (order_id,))
    doors = [row[0] for row in cursor.fetchall()]
    conn.close()
    return doors

def send_order_update(order_id, action, action_time=None, store_on_fail=True):
    """
    Notifies the API that an order was picked up or opened, including action_time if provided.
    When store_on_fail is True, an unsynced action is inserted on failure.
    """
    payload = {"api_key": API_KEY, "order_id": order_id, "action": action}
    if action_time:
        payload["action_time"] = action_time

    try:
        response = requests.get(API_URL + "update_order_pickup.php", params=payload)
        if response.status_code == 200:
            print(f"Successfully updated {action} for order {order_id}")
            return True
    except requests.exceptions.RequestException:
        print(f"Failed to sync {action} for order {order_id}.")

    if store_on_fail:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if action_time:
            cursor.execute("INSERT INTO offline_actions (order_id, action, action_time) VALUES (?, ?, ?)", 
                           (order_id, action, action_time))
        else:
            cursor.execute("INSERT INTO offline_actions (order_id, action) VALUES (?, ?)", 
                           (order_id, action))
        conn.commit()
        conn.close()
    return False

def open_relays(doors):
    """Sends relay commands to Arduino to open specific doors in one batch."""
    if not doors:
        return
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)
        relay_commands = [f"{door}:{i*500}:1000" for i, door in enumerate(doors)]
        command = f"OPEN:{','.join(relay_commands)}\n"
        ser.write(command.encode())
        print(f"Sent command: {command.strip()}")
        ser.readline()
        ser.close()
    except Exception as e:
        print(f"Error opening relays: {e}")

def scan_qr_codes():
    """
    Continuously captures an image using rpicam-still, then decodes any QR codes found.
    """
    output_path = os.path.expanduser("~/test.jpg")
    cmd = ["rpicam-still", "-t", "10", "-o", output_path]

    while True:
        print("Capturing image...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("Error capturing image:")
            print(result.stderr)
        else:
            print(f"Image captured and saved to {output_path}")
            image = cv2.imread(output_path)
            if image is None:
                print("Failed to load the captured image.")
            else:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                decoded_objects = decode(gray)
                for obj in decoded_objects:
                    code = obj.data.decode("utf-8")
                    print(f"QR Code Detected: {code}")
                    order_id, action = fetch_order_by_code(code)
                    if order_id:
                        print(f"Valid {action} for Order: {order_id}")
                        send_order_update(order_id, action)
                        doors = fetch_door_items(order_id)
                        open_relays(doors)
                        time.sleep(3)
        time.sleep(2)

def process_code(code):
    order_id, action = fetch_order_by_code(code)
    print(f"Keypad code processed: {order_id}, {action}")
    if order_id and action in ('pickup', 'opening'):
        lcd.clear()
        lcd.write_string("Accepted order:")
        lcd.cursor_pos = (1, 0)
        lcd.write_string(f"{order_id}")
        time.sleep(2)
        doors = fetch_door_items(order_id)
        lcd.clear()
        lcd.write_string(f"Opening door {','.join(doors)}")
        open_relays(doors)
        time.sleep(10)
        send_order_update(order_id, action)
        lcd.clear()
        return True
    elif order_id and action == 'already_picked_up':
        lcd.clear()
        lcd.write_string("Order already picked up!")
        time.sleep(3)
        return True
    elif order_id and action == 'not_in_opening_window':
        lcd.clear()
        lcd.write_string("Booking not active!")
        time.sleep(3)
        return True
    elif order_id and action == 'opening_not_configured':
        lcd.clear()
        lcd.write_string("ERROR: Opening not configured!")
        time.sleep(3)
        return True
    else:
        return False

# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------
def main():
    """Main function handling keypad scanning and starting background threads."""
    initialize_database()

    # Start background threads
    threading.Thread(target=orders_sync_loop, daemon=True).start()    # Sync orders from the API
    threading.Thread(target=offline_sync_loop, daemon=True).start()     # Sync offline actions
    # threading.Thread(target=scan_qr_codes, daemon=True).start()       # Uncomment to enable QR scanning

    entered_code = ""
    last_input_time = None
    lcd.clear()
    lcd.backlight_enabled = False

    try:
        while True:
            key = read_keypad()
            if key is not None:
                last_input_time = time.time()
                if key == '*':
                    if not entered_code:
                        lcd.backlight_enabled = True
                        lcd.clear()
                        lcd.write_string("Enter Code:")
                        last_input_time = time.time()
                    else:
                        print(f"Entered code: {entered_code}")
                        if entered_code == OPEN_ALL_CODE:
                            lcd.clear()
                            lcd.write_string("Opening ALL doors")
                            open_relays(ALL_DOORS)  # ALL_DOORS is a list of door identifiers
                            time.sleep(10)
                            lcd.clear()
                        else:
                            lcd.clear()
                            lcd.write_string("Checking...")
                            if not process_code(entered_code):
                                lcd.clear()
                                lcd.write_string("Checking online")
                                fetch_orders_now()  # Update the database
                                if not process_code(entered_code):
                                    lcd.clear()
                                    lcd.write_string("Invalid Code!")
                                    time.sleep(3)
                        entered_code = ""
                        lcd.clear()
                        lcd.backlight_enabled = False
                        last_input_time = None
                elif key == '#':
                    entered_code = ""
                    lcd.clear()
                    lcd.write_string("Enter Code:")
                    last_input_time = time.time()
                else:
                    entered_code += str(key)
                    lcd.clear()
                    lcd.write_string(f"Enter Code:\n{entered_code}")
                    last_input_time = time.time()
                time.sleep(0.3)
            else:
                if last_input_time and (time.time() - last_input_time >= LCD_TIMEOUT):
                    lcd.clear()
                    lcd.backlight_enabled = False
                    entered_code = ""
                    last_input_time = None
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        lcd.clear()
        lcd.backlight_enabled = False
        GPIO.cleanup()

if __name__ == "__main__":
    main()
