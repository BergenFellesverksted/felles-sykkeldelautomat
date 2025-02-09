import time
import requests
import sqlite3
import serial
from RPi import GPIO
from RPLCD.i2c import CharLCD
from constants import *

# Constants
SERIAL_PORT = "/dev/ttyUSB0"  # Adjust for the Arduino connection
DELAY_BETWEEN_GROUPS = 0.5  # Delay (in seconds) after every 2 relays

# Keypad Configuration
KEYPAD = [
    [1, 2, 3, 'A'],
    [4, 5, 6, 'B'],
    [7, 8, 9, 'C'],
    ['*', 0, '#', 'D']
]
ROW_PINS = [12, 16, 20, 21]  # GPIO row pins
COL_PINS = [25, 8, 7, 1]     # GPIO column pins

# LCD Initialization
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
lcd.backlight_enabled = False  # Keep LCD off initially

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(ROW_PINS, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(COL_PINS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

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
    """Checks if the entered code exists in the local database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT order_id FROM orders 
        WHERE pickup_code = ? OR return_code = ?
    """, (code, code))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def fetch_door_items(order_id):
    """Fetches doors associated with items in an order."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT door FROM order_items 
        WHERE order_id = ?
    """, (order_id,))
    doors = [row[0] for row in cursor.fetchall()]
    conn.close()
    return doors

def send_order_update(order_id):
    """Notifies the remote API that an order has been picked up."""
    payload = {"api_key": API_KEY, "order_id": order_id, "action": "pickup"}
    try:
        response = requests.get(API_URL, params=payload)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Error sending order update: {e}")
        return False

def open_relays(doors):
    """
    Sends relay commands to Arduino to open specific doors.
    - Adds a small delay after every 2 relays.
    """
    if not doors:
        return
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)  # Wait for serial connection

        relay_groups = []
        for i in range(0, len(doors), 2):  # Process 2 doors at a time
            group = doors[i:i + 2]
            relay_commands = [f"{door}:500:3000" for door in group]  # 500ms wait, 3000ms duration
            relay_groups.append(",".join(relay_commands))

        for group in relay_groups:
            command = f"OPEN:{group}\n"
            ser.write(command.encode())
            print(f"Sent command: {command.strip()}")
            ser.readline()  # Read response
            time.sleep(DELAY_BETWEEN_GROUPS)  # Small delay after every 2 doors

        ser.close()
    except Exception as e:
        print(f"Error opening relays: {e}")

def main():
    entered_code = ""
    lcd.clear()
    lcd.backlight_enabled = False
    code_entered = False

    try:
        while True:
            key = read_keypad()
            if key is not None:
                if key == '*':  # Wake up the screen and start collecting input
                    if not entered_code:
                        lcd.backlight_enabled = True
                        lcd.clear()
                        lcd.write_string("Enter Code:")
                    elif entered_code:  # Second '*' means submit
                        lcd.clear()
                        lcd.write_string("Checking...")
                        order_id = fetch_order_by_code(entered_code)

                        if order_id:
                            lcd.clear()
                            lcd.write_string(f"Order: {order_id}\nOpening...")
                            send_order_update(order_id)  # Notify API
                            doors = fetch_door_items(order_id)
                            open_relays(doors)  # Open the corresponding doors
                            time.sleep(3)
                            lcd.clear()
                            lcd.write_string("Done!")
                        else:
                            lcd.clear()
                            lcd.write_string("Invalid Code!")
                            time.sleep(2)
                        
                        entered_code = ""  # Reset code
                        lcd.clear()
                        lcd.backlight_enabled = False
                elif key == '#':  # Reset input
                    entered_code = ""
                    lcd.clear()
                    lcd.write_string("Enter Code:")
                else:
                    entered_code += str(key)
                    lcd.clear()
                    lcd.write_string(f"Enter Code:\n{entered_code}")

                time.sleep(0.3)  # Debounce

    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        lcd.clear()
        lcd.backlight_enabled = False
        GPIO.cleanup()

if __name__ == "__main__":
    main()
