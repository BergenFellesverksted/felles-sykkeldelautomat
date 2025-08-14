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
from constants import *  # DB_FILE, API_URL, API_KEY, OPEN_ALL_CODE, ALL_DOORS, SERIAL_PORT, etc.

# ------------------------------------------------------------------------------
# SAFE TEST TOGGLES (no side effects)
# ------------------------------------------------------------------------------
SAFE_NO_SEND = True              # do not call update_order_pickup.php
SAFE_NO_OPEN = True              # do not touch the relays/serial
SAFE_PRESERVE_OFFLINE = True     # keep existing offline_actions UNSYNCED during tests

def _safe_log(msg: str):
    print(f"[SAFE] {msg}")

if SAFE_NO_SEND or SAFE_NO_OPEN:
    enabled = []
    if SAFE_NO_SEND:
        enabled.append("NO_SEND")
    if SAFE_NO_OPEN:
        enabled.append("NO_OPEN")
    if SAFE_PRESERVE_OFFLINE:
        enabled.append("PRESERVE_OFFLINE")
    _safe_log("SAFE MODE enabled: " + ", ".join(enabled))

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
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
# Helpers
# ------------------------------------------------------------------------------
def _normalize_flag_text(v):
    return (str(v or '')).strip().lower()

def _is_not_picked_flag(v):
    # Treat these as "not picked yet"
    return _normalize_flag_text(v) in ('', 'not picked up', 'not picked', 'none', 'null', '0')

def _parse_when(s):
    """Best-effort parser for timestamps; returns datetime or None."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    # common noise removals
    if t.endswith('Z'):
        t = t[:-1]
    if t.upper().endswith(' UTC'):
        t = t[:-4]
    try:
        return datetime.fromisoformat(t)
    except Exception:
        pass
    for fmt in (
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%dT%H:%M:%S',
    ):
        try:
            return datetime.strptime(t, fmt)
        except Exception:
            continue
    return None

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
# Console-driven keypad: prompt first, then feed '*' + code + '*'
# ------------------------------------------------------------------------------
_console_queue = []

def read_keypad():
    """Reads 'key presses'. In console mode, prompt for a code and feed '*' + code + '*'."""
    if _console_queue:
        k = _console_queue.pop(0)
        print(f"[KEYPAD] {repr(k)}")
        return k

    try:
        code_line = input("Please enter code: ").strip()
    except KeyboardInterrupt:
        raise
    except Exception:
        code_line = ""

    if code_line == "":
        # no input; emulate idle
        return None

    # Enqueue synthetic sequence: '*' (open), characters, '*' (submit)
    _console_queue.extend(['*'] + list(code_line) + ['*'])
    k = _console_queue.pop(0)
    print(f"[KEYPAD] {repr(k)}")
    return k

# ------------------------------------------------------------------------------
# Lookup & validation
# ------------------------------------------------------------------------------
def fetch_order_by_code(code):
    """
    Fetches an order by its code.

    For a pickup code:
      - If the order has not been picked up, it is valid.
      - If the order was picked up, the code remains valid if within MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP
        minutes of the pickup time; otherwise returns (order_id, 'already_picked_up').

    For an opening code:
      - Valid only if current time is between start_time and end_time; else returns
        (order_id, 'not_in_opening_window').

    If a recent unsynced offline action (< 15 minutes) exists for the order, we block (None, None).
    If no order is found, returns (None, None).
    """
    code_raw = code or ""
    code_trim = code_raw.strip()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Case-insensitive + trimmed matching to fix issues like 'c2c9' vs 'C2C9' and stray spaces
    cursor.execute("""
        SELECT order_id, pickup_code, pickup_time, opening_code, start_time, end_time
        FROM orders
        WHERE TRIM(pickup_code) COLLATE NOCASE = TRIM(?)
           OR TRIM(opening_code) COLLATE NOCASE = TRIM(?)
    """, (code_trim, code_trim))
    order = cursor.fetchone()

    if order is None:
        conn.close()
        print(f"[DEBUG] No order matched code='{code_trim}'. Check case/spaces in DB.")
        return (None, None)
    
    order_id, pickup_code, pickup_time, opening_code, start_time, end_time = order

    # Determine which field matched (for debugging)
    matched_via = None
    if pickup_code and str(pickup_code).strip().lower() == code_trim.lower():
        matched_via = 'pickup_code'
    elif opening_code and str(opening_code).strip().lower() == code_trim.lower():
        matched_via = 'opening_code'
    print(f"[DEBUG] Code matched order_id={order_id} via {matched_via}. "
          f"pickup_time={pickup_time!r}, start_time={start_time!r}, end_time={end_time!r}")

    # Block if recent unsynced offline action
    earliest_accepted_time = datetime.now() - timedelta(minutes=MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP)
    cursor.execute("""
        SELECT id FROM offline_actions
        WHERE order_id = ? AND synced = 0 AND datetime(action_time) > ?
    """, (order_id, earliest_accepted_time.isoformat(' ')))
    offline_action = cursor.fetchone()
    if offline_action:
        conn.close()
        print(f"[DEBUG] Order {order_id} blocked by recent unsynced offline action.")
        return (None, None)

    action = None
    # Pickup path
    if matched_via == 'pickup_code':
        if _is_not_picked_flag(pickup_time):
            action = 'pickup'
        else:
            pickup_dt = _parse_when(pickup_time)
            if pickup_dt is None:
                # Be tolerant: treat unparsable as "not picked yet" instead of failing hard
                print(f"[DEBUG] Unparsable pickup_time={pickup_time!r}; treating as NOT picked.")
                action = 'pickup'
            else:
                if datetime.now() <= pickup_dt + timedelta(minutes=MINUTES_TO_ACCEPT_ORDER_AFTER_PICKUP):
                    action = 'pickup'
                else:
                    conn.close()
                    print(f"[DEBUG] Order {order_id} already picked up beyond grace period.")
                    return (order_id, 'already_picked_up')

    # Opening path
    elif matched_via == 'opening_code':
        st_bad = (start_time is None) or (_normalize_flag_text(start_time) in ('', 'not started'))
        et_bad = (end_time is None) or (_normalize_flag_text(end_time) in ('', 'not ended'))
        if st_bad or et_bad:
            conn.close()
            print(f"[DEBUG] Opening window not configured correctly for order {order_id}.")
            return (order_id, 'opening_not_configured')

        start_dt = _parse_when(start_time)
        end_dt = _parse_when(end_time)
        if not start_dt or not end_dt:
            conn.close()
            print(f"[DEBUG] Could not parse opening window for order {order_id}.")
            return (None, None)
        if start_dt <= datetime.now() <= end_dt:
            action = 'opening'
        else:
            conn.close()
            print(f"[DEBUG] Not in opening window for order {order_id}. Now not in [{start_dt}, {end_dt}].")
            return (order_id, 'not_in_opening_window')

    else:
        conn.close()
        print(f"[DEBUG] Internal: code matched neither pickup nor opening? code='{code_trim}'")
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

    SAFE MODE behavior:
      - Do NOT perform the HTTP request when SAFE_NO_SEND is True.
      - Do NOT insert offline_actions.
      - Return True for normal calls so the flow continues.
      - During offline sync passes (store_on_fail=False with action_time), return False
        if SAFE_PRESERVE_OFFLINE is True, to avoid marking offline rows as 'synced'.
    """
    payload = {"api_key": API_KEY, "order_id": order_id, "action": action}
    if action_time:
        payload["action_time"] = action_time

    # ---- SAFE MODE: no network updates ----
    if SAFE_NO_SEND:
        if store_on_fail is False and action_time is not None and SAFE_PRESERVE_OFFLINE:
            _safe_log(f"Skip sending (offline sync pass) order={order_id} action={action} time={action_time} "
                      f"-> returning False so existing offline_actions remain UNSYNCED")
            return False  # prevents sync_offline_actions from marking as synced
        _safe_log(f"Skip sending update: would GET {API_URL}update_order_pickup.php params={payload} -> returning True")
        return True

    # ---- ORIGINAL NETWORK PATH (unchanged) ----
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
    relay_commands = [f"{door}:{i*500}:1000" for i, door in enumerate(doors)]
    command = f"OPEN:{','.join(relay_commands)}"

    # ---- SAFE MODE: no relay activation ----
    if SAFE_NO_OPEN:
        _safe_log(f"Skip opening relays; would send -> {command}")
        return

    # ---- ORIGINAL SERIAL PATH (unchanged) ----
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)
        ser.write((command + "\n").encode())
        print(f"Sent command: {command}")
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
def _start_background_threads():
    threading.Thread(target=orders_sync_loop, daemon=True).start()    # Sync orders from the API
    threading.Thread(target=offline_sync_loop, daemon=True).start()   # Sync offline actions

def main():
    """Main function handling keypad scanning and starting background threads."""
    initialize_database()

    entered_code = ""
    last_input_time = None
    lcd.clear()
    lcd.backlight_enabled = False

    # Start by prompting for a code first
    threads_started = False

    try:
        while True:
            key = read_keypad()  # blocks for console input, returns '*', code chars, then '*'
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
                        if entered_code.strip() == str(OPEN_ALL_CODE):
                            lcd.clear()
                            lcd.write_string("Opening ALL doors")
                            open_relays(ALL_DOORS)  # list of door identifiers
                            time.sleep(10)
                            lcd.clear()
                        else:
                            lcd.clear()
                            lcd.write_string("Checking...")
                            if not process_code(entered_code):
                                lcd.clear()
                                lcd.write_string("Checking online")
                                fetch_orders_now()  # Update the database from API
                                if not process_code(entered_code):
                                    lcd.clear()
                                    lcd.write_string("Invalid Code!")
                                    time.sleep(3)
                        entered_code = ""
                        lcd.clear()
                        lcd.backlight_enabled = False
                        last_input_time = None

                        # Start background threads after first submission
                        if not threads_started:
                            _start_background_threads()
                            threads_started = True

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
