import time
import requests
import serial
from constants import API_URL, API_KEY, SERIAL_PORT

def open_door(door_number):
    """
    Sends a command via the serial port to open a specific door.
    Adjust the command format to match your Arduino/relay requirements.
    """
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)  # Give time for the connection to initialize
        # Example command format; adjust as needed:
        command = f"OPEN:{door_number}:500:1000\n"
        ser.write(command.encode())
        # Optionally, wait for a response:
        response = ser.readline().decode().strip()
        print(f"Serial response: {response}")
        ser.close()
        return True
    except Exception as e:
        print(f"Error opening door {door_number}: {e}")
        return False

def mark_request_executed(request_id):
    """
    Notifies the website that the door command with request_id has been executed.
    """
    payload = {"api_key": API_KEY, "request_id": request_id}
    try:
        r = requests.post(API_URL + "mark_request_executed.php", data=payload)
        if r.status_code == 200:
            print(f"Request {request_id} marked as executed.")
        else:
            print(f"Error marking request {request_id} executed: {r.text}")
    except Exception as e:
        print(f"Exception marking request {request_id} executed: {e}")

def poll_door_requests():
    """
    Polls the website for pending door open requests and processes them.
    """
    while True:
        try:
            response = requests.get(API_URL + "get_door_requests.php", params={"api_key": API_KEY})
            if response.status_code == 200:
                requests_data = response.json()
                for req in requests_data:
                    request_id = req.get('id')
                    door_number = req.get('door_number')
                    print(f"Processing door {door_number} request id {request_id}")
                    if open_door(door_number):
                        mark_request_executed(request_id)
            else:
                print(f"Error: {response.status_code} {response.text}")
        except Exception as e:
            print("Error polling door requests:", e)
        time.sleep(5)  # Poll every 5 seconds

if __name__ == "__main__":
    poll_door_requests()
