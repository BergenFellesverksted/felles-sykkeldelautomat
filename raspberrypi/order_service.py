import time
import requests
import sqlite3
import serial
import threading
import subprocess
import os
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from RPi import GPIO
from RPLCD.i2c import CharLCD
from constants import *  # Make sure DB_FILE, API_URL, API_KEY, etc. are defined here

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
SERIAL_PORT = "/dev/ttyUSB0"
DELAY_BETWEEN_GROUPS = 0.5
OFFLINE_SYNC_INTERVAL = 300   # 5 minutes for syncing offline actions
ORDERS_SYNC_INTERVAL = 60     # Sync orders every 60 seconds
LCD_TIMEOUT = 20 # Time before the LCD screen turns off without an input

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

    # Table for orders fetched from the API
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
            action TEXT CHECK(action IN ('pickup', 'return')),
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
        # Adjust the URL formatting as needed.
        response = requests.get(f"{API_URL}orders.php?api_key={API_KEY}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching orders: {e}")
        return []

def update_local_database(orders):
    """Update the local SQLite database with new/updated orders."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for order in orders:
        # If a key is missing, default to None
        return_code = order.get("return_code", None)
        return_time = order.get("return_time", None)

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
            order["order_id"],
            order["customer_name"],
            order["order_date"],
            order["order_total"],
            order["pickup_code"],
            order["pickup_time"],
            return_code,
            return_time
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

def orders_sync_loop():
    """Loop that periodically syncs orders from the API."""
    while True:
        print("Fetching orders...")
        orders = fetch_orders()
        if orders:
            update_local_database(orders)
            print(f"Updated {len(orders)} orders.")
        else:
            print("No new orders found.")
        time.sleep(ORDERS_SYNC_INTERVAL)

# ------------------------------------------------------------------------------
# Offline Actions Sync (runs in its own thread)
# ------------------------------------------------------------------------------
def sync_offline_actions():
    """Attempts to sync offline actions with the API."""
    print(f"Checking offline pickups")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, order_id, action FROM offline_actions WHERE synced = 0")
    unsynced_actions = cursor.fetchall()

    for action_id, order_id, action in unsynced_actions:
        if send_order_update(order_id, action):
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
    """Fetches a valid order that hasn't been completed."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.order_id,
            CASE 
                WHEN o.pickup_code = ? 
                     AND (o.pickup_time IS NULL OR o.pickup_time = 'Not Picked Up')
                     THEN 'pickup'
                WHEN o.return_code = ? 
                     AND (o.return_time IS NULL OR o.return_time = 'Not Returned')
                     THEN 'return'
            END AS action
        FROM orders o
        LEFT JOIN offline_actions a 
             ON o.order_id = a.order_id AND a.synced = 0
        WHERE (
                (o.pickup_code = ? AND (o.pickup_time IS NULL OR o.pickup_time = 'Not Picked Up'))
             OR (o.return_code = ? AND (o.return_time IS NULL OR o.return_time = 'Not Returned'))
              )
          AND a.order_id IS NULL;
    """, (code, code, code, code))
    result = cursor.fetchone()
    conn.close()
    return result if result else (None, None)

def fetch_door_items(order_id):
    """Fetches doors associated with items in an order."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT door FROM order_items WHERE order_id = ?", (order_id,))
    doors = [row[0] for row in cursor.fetchall()]
    conn.close()
    return doors

def send_order_update(order_id, action):
    """Notifies the API that an order was picked up or returned."""
    payload = {"api_key": API_KEY, "order_id": order_id, "action": action}
    try:
        response = requests.get(API_URL + "update_order_pickup.php", params=payload)
        if response.status_code == 200:
            print(f"Successfully updated {action} for order {order_id}")
            return True
    except requests.exceptions.RequestException:
        print(f"Failed to sync {action} for order {order_id}. Storing for later.")
    
    # Store the unsynced action locally
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO offline_actions (order_id, action) VALUES (?, ?)", (order_id, action))
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
    Continuously captures an image using rpicam-still, then reads the image and
    decodes any QR codes found.
    """
    output_path = os.path.expanduser("~/test.jpg")
    # The command to capture an image. Adjust the timeout (-t) as needed.
    cmd = ["rpicam-still", "-t", "10", "-o", output_path]

    while True:
        print("Capturing image...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("Error capturing image:")
            print(result.stderr)
        else:
            print(f"Image captured and saved to {output_path}")
            # Read the captured image
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
                        # Pause to prevent processing the same QR code repeatedly
                        time.sleep(3)
        # Wait a few seconds before capturing the next image
        time.sleep(2)

# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------
def main():
    """Main function handling keypad scanning and starting all background threads."""
    initialize_database()

    # Start background threads:
    threading.Thread(target=orders_sync_loop, daemon=True).start()    # Sync orders from the API
    threading.Thread(target=offline_sync_loop, daemon=True).start()     # Sync any offline actions
    #threading.Thread(target=scan_qr_codes, daemon=True).start()         # Continuously scan QR codes

    entered_code = ""
    last_input_time = None
    lcd.clear()
    lcd.backlight_enabled = False

    try:
        while True:
            key = read_keypad()
            if key is not None:
                # Update the last key press time
                last_input_time = time.time()
                
                if key == '*':
                    if not entered_code:
                        # First press of '*' turns on the backlight and prompts for a code.
                        lcd.backlight_enabled = True
                        lcd.clear()
                        lcd.write_string("Enter Code:")
                        last_input_time = time.time()
                    elif entered_code:
                        print(f"Entered code: {entered_code}")
                        # Check if the entered code matches the special "open all doors" code.
                        if entered_code == OPEN_ALL_CODE:
                            lcd.clear()
                            lcd.write_string("Opening ALL doors")
                            open_relays(ALL_DOORS)  # ALL_DOORS is a list of door identifiers from constants.py
                            time.sleep(10)
                            lcd.clear()
                        else:
                            # When '*' is pressed and a code has been entered, check the code.
                            lcd.clear()
                            lcd.write_string("Checking...")
                            order_id, action = fetch_order_by_code(entered_code)
                            print(f"Keypad code processed: {order_id}, {action}")
                            if order_id:
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
                            else:
                                lcd.clear()
                                lcd.write_string("Invalid Code!")
                                time.sleep(3)
                        # Reset code and screen after processing.
                        entered_code = ""
                        lcd.clear()
                        lcd.backlight_enabled = False
                        last_input_time = None

                elif key == '#':
                    # '#' clears any code that was entered.
                    entered_code = ""
                    lcd.clear()
                    lcd.write_string("Enter Code:")
                    last_input_time = time.time()  # Reset timer on clear

                else:
                    # For any other key, append to the code and update the display.
                    entered_code += str(key)
                    lcd.clear()
                    lcd.write_string(f"Enter Code:\n{entered_code}")
                    last_input_time = time.time()

                # Small delay to debounce and prevent reading the same key repeatedly.
                time.sleep(0.3)
            else:
                # No key was pressed in this cycle.
                # If the user has started entering a code, check for a 20-second timeout.
                if last_input_time and (time.time() - last_input_time >= LCD_TIMEOUT):
                    # Timeout reached: clear the entered code and turn off the backlight.
                    lcd.clear()
                    lcd.backlight_enabled = False
                    entered_code = ""
                    last_input_time = None
                # A short sleep to avoid busy-waiting.
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        lcd.clear()
        lcd.backlight_enabled = False
        GPIO.cleanup()

if __name__ == "__main__":
    main()
