import time
from RPi import GPIO

# GPIO setup for the 4x4 keypad
KEYPAD = [
    [1, 2, 3, 'A'],
    [4, 5, 6, 'B'],
    [7, 8, 9, 'C'],
    ['*', 0, '#', 'D']
]

ROW_PINS = [12, 16, 20, 21]  # GPIO pins connected to the row pins of the keypad
COL_PINS = [25, 8, 7, 1]   # GPIO pins connected to the column pins of the keypad

# Set up GPIO pins
GPIO.setmode(GPIO.BCM)
GPIO.setup(ROW_PINS, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(COL_PINS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def read_keypad():
    """Scans the keypad and returns the pressed key."""
    for row_num, row_pin in enumerate(ROW_PINS):
        GPIO.output(row_pin, GPIO.HIGH)
        col_states = [GPIO.input(col_pin) for col_pin in COL_PINS]
        for col_num, col_pin in enumerate(COL_PINS):
            if GPIO.input(col_pin) == GPIO.HIGH:
                GPIO.output(row_pin, GPIO.LOW)
                return KEYPAD[row_num][col_num]
        GPIO.output(row_pin, GPIO.LOW)
    return None


def main():
    """Main function to capture keypad input."""
    try:
        while True:
            key = read_keypad()
            if key is not None:
                print(f"Key Pressed: {key}")
                time.sleep(0.3)  # Debounce delay

    except KeyboardInterrupt:
        print("Exiting program")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
