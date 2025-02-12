import subprocess
import time
import os
import cv2
from pyzbar.pyzbar import decode

def main():
    # Expand the tilde (~) to your home directory
    output_path = os.path.expanduser("~/test.jpg")
    
    # Command to capture an image using rpicam-still.
    # Adjust the timeout (-t) as needed.
    cmd = ["rpicam-still", "-t", "10", "hflip", "-o", output_path]

    while True:
        print("Capturing image...")
        # Run the command; capture output in case you need to debug errors
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("Error capturing image:")
            print(result.stderr)
        else:
            print(f"Image captured and saved to {output_path}")
            
            # Load the captured image
            image = cv2.imread(output_path)
            if image is None:
                print("Failed to load the captured image.")
            else:
                # Convert image to grayscale for QR code detection
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                # Decode any QR codes in the image
                detector = cv2.QRCodeDetector()
                data, bbox, straight_qrcode = detector.detectAndDecode(image)
                print(data, bbox, straight_qrcode)

        # Wait a few seconds before capturing the next image
        time.sleep(2)

if __name__ == "__main__":
    main()
