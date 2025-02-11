import time
import requests
import sqlite3
import serial
import threading
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from RPi import GPIO
from RPLCD.i2c import CharLCD
from constants import *

# Constants
SERIAL_PORT = "/dev/ttyUSB0"
DELAY_BETWEEN_GROUPS = 0.5
SYNC_INTERVAL = 300  # 5 minutes between trying to send offline codes

# Keypad Configuration
KEYPAD = [
    [1, 2, 3, 'A'],
    [4, 5, 6, 'B'],
    [7, 8, 9, 'C'],
    ['*', 0, '#', 'D']
]
ROW_PINS = [12, 16, 20, 21]
COL_PINS = [25, 8, 7, 1]

# LCD Initialization
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
lcd.backlight_enabled = False

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(ROW_PINS, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(COL_PINS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def initialize_database():
    """Creates the necessary tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

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

    # Ensure pickup/return time is empty and the order isn't in offline_actions
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
        print(API_URL + "update_order_pickup.php")
        print(payload)
        if response.status_code == 200:
            print(f"Successfully updated {action} for order {order_id}")
            return True
    except requests.exceptions.RequestException:
        print(f"Failed to sync {action} for order {order_id}. Storing for later.")
    
    # If failed, store it in offline_actions
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO offline_actions (order_id, action) VALUES (?, ?)", (order_id, action))
    conn.commit()
    conn.close()
    return False

def sync_offline_actions():
    """Attempts to sync offline actions with the API."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, order_id, action FROM offline_actions WHERE synced = 0")
    unsynced_actions = cursor.fetchall()

    for action_id, order_id, action in unsynced_actions:
        if send_order_update(order_id, action):
            cursor.execute("UPDATE offline_actions SET synced = 1 WHERE id = ?", (action_id,))
    
    conn.commit()
    conn.close()

def open_relays(doors):
    """Sends relay commands to Arduino to open specific doors in one batch."""
    if not doors:
        return
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)

        relay_commands = [f"{door}:{i*500}:5000" for i, door in enumerate(doors)]
        command = f"OPEN:{','.join(relay_commands)}\n"
        ser.write(command.encode())
        print(f"Sent command: {command.strip()}")

        ser.readline()
        ser.close()
    except Exception as e:
        print(f"Error opening relays: {e}")

def scan_qr_codes():
    """Continuously scans QR codes."""
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
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

        time.sleep(0.5)

    cap.release()

def main():
    """Main function handling both keypad and QR scanning."""
    initialize_database()
    #threading.Thread(target=scan_qr_codes, daemon=True).start()
    #threading.Thread(target=lambda: time.sleep(SYNC_INTERVAL) or sync_offline_actions(), daemon=True).start()

    entered_code = ""
    lcd.clear()
    lcd.backlight_enabled = False

    try:
        while True:
            key = read_keypad()
            if key is not None:
                if key == '*':
                    if not entered_code:
                        lcd.backlight_enabled = True
                        lcd.clear()
                        lcd.write_string("Enter Code:")
                    elif entered_code:
                        lcd.clear()
                        lcd.write_string("Checking...")
                        order_id, action = fetch_order_by_code(entered_code)

                        print(order_id, action)

                        if order_id:
                            lcd.clear()
                            lcd.write_string(f"Order: {order_id}\n{action.capitalize()}...")
                            send_order_update(order_id, action)
                            doors = fetch_door_items(order_id)
                            open_relays(doors)
                            time.sleep(3)
                            lcd.clear()
                            lcd.write_string("Done!")
                        else:
                            lcd.clear()
                            lcd.write_string("Invalid Code!")
                            time.sleep(2)

                        entered_code = ""
                        lcd.clear()
                        lcd.backlight_enabled = False
                elif key == '#':
                    entered_code = ""
                    lcd.clear()
                    lcd.write_string("Enter Code:")
                else:
                    entered_code += str(key)
                    lcd.clear()
                    lcd.write_string(f"Enter Code:\n{entered_code}")

                time.sleep(0.3)

    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        lcd.clear()
        lcd.backlight_enabled = False
        GPIO.cleanup()

if __name__ == "__main__":
    main()
