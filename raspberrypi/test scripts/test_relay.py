import serial
import time

def open_relays(relays):
    """
    Sends a command to the Arduino Mega to open specific relays with custom wait times and durations.
    
    Args:
        relays (dict): Dictionary where keys are relay numbers and values are (wait time, duration) tuples.
    """
    try:
        # Establish serial connection to the Arduino Mega
        ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)  # Adjust for correct serial port
        time.sleep(2)  # Allow time for the connection to stabilize

        # Convert the relay dictionary to a formatted string
        relays_command = ','.join(f"{relay}:{wait}:{duration}" for relay, (wait, duration) in relays.items())
        command = f"OPEN:{relays_command}\n"

        # Send the command to the Arduino
        ser.write(command.encode())
        print(f"Sent command: {command.strip()}")

        # Read response (optional)
        response = ser.readline().decode('utf-8').strip()
        print(f"Arduino response: {response}")

        # Close the serial connection
        ser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Example: Relay 1 will open after 1000ms and stay open for 3000ms, Relay 2 will open after 2000ms and stay open for 5000ms
    relays_to_open = {
        14: (1000, 10000),  # Relay 1 → Wait 1000ms → Open for 3000ms
    }
    open_relays(relays_to_open)
