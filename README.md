# FELLES Sykkeldelautomat

This document describes the setup, hardware, software, and integration of the FELLES Sykkeldelautomat - a bike part vending machine built from an IKEA Kallax shelf with electronically controlled locker doors.

---

## Table of Contents

- [Overview](#overview)
- [System Highlights](#system-highlights)
- [Hardware Overview](#hardware-overview)
- [Wiring and Pinouts](#wiring-and-pinouts)
  - [Raspberry Pi ↔ I²C LCD](#raspberry-pi--i²c-lcd)
  - [Raspberry Pi ↔ 4×4 Matrix Keypad](#raspberry-pi--4x4-matrix-keypad)
  - [Arduino Mega 2560 ↔ Relay Boards](#arduino-mega-2560--relay-boards)
- [Raspberry Pi Software](#raspberry-pi-software)
  - [order_service.py](#orderservicepy)
  - [online_unlocks.py](#online_unlockspy)
  - [constantsTemplate.py](#constantstemplatepy)
  - [Test Scripts](#test-scripts)
  - [Systemd Services](#systemd-services)
- [Website API and WooCommerce Integration](#website-api-and-woocommerce-integration)
  - [WooCommerce Hooks](#woocommerce-hooks)
  - [API Endpoints](#api-endpoints)
  - [Admin Web Interface](#admin-web-interface)
- [Setup Guide](#setup-guide)
  - [1. Hardware Assembly and Wiring](#1-hardware-assembly-and-wiring)
  - [2. Raspberry Pi Software Setup](#2-raspberry-pi-software-setup)
  - [3. Arduino Firmware Setup](#3-arduino-firmware-setup)
  - [4. WooCommerce and Server Setup](#4-woocommerce-and-server-setup)
  - [5. Maintenance and Use](#5-maintenance-and-use)

---

## Overview

This repository contains the files and instructions needed to build your own **Sykkeldelautomat** (bike part vending machine) or to maintain the one at FELLES SykkelLab.

The **FELLES Sykkeldelautomat** integrates a Raspberry Pi, an Arduino Mega 2560, and two 16-channel relay boards to control 12V electronic cabinet locks mounted on a modified IKEA Kallax shelf. The system interacts with a WooCommerce online store to manage item orders and pickups using unique pickup and return codes.

Items are ordered through the [BergenFellesverksted.no](https://bergenfellesverksted.no) WooCommerce online store. When an item belongs to the Sykkeldelautomat category, a pickup code is automatically sent to the buyer. Additionally, each item is assigned a door using a WooCommerce `attribute` formatted as `Door = NN`.

---

## System Highlights

- **Raspberry Pi 3B+:**
  - Runs software to manage user inputs via a 4×4 matrix keypad.
  - Outputs feedback on an I²C LCD display.
  - Communicates with an Arduino over USB and with a remote API.

- **Arduino Mega 2560:**
  - Controls relays that power the 12V locks.
  - Listens for serial commands from the Raspberry Pi.

- **WooCommerce Integration:**
  - A set of custom functions assigns unique pickup/return/opening codes to orders and bookings.
  - API endpoints allow the Raspberry Pi to fetch new orders and report pickups.

- **Remote Administration:**
  - A web interface allows admins to send unlock commands to individual doors.

---

## Hardware Overview

- **Modified IKEA Kallax Shelf:**  
  Used as the cabinet with custom locker-style doors.

- **12V Electronic Cabinet Locks:**  
  Each door is secured by a lock activated when 12V power is applied.

- **Two 16-Channel Relay Boards:**  
  - **Relay Board 1:** Controls doors 1–16 using Arduino’s odd-numbered pins.
  - **Relay Board 2:** Controls doors 17–20 (and extra channels for future expansion) using Arduino’s even-numbered pins.

- **Arduino Mega 2560:**  
  Manages digital outputs to the relay boards and communicates with the Raspberry Pi via USB.

- **Raspberry Pi 3B+:**  
  Handles user input (keypad), output (LCD), and network communication with the web API.

- **Power Supplies:**  
  Separate 5V (for Pi and Arduino) and 12V (for the locks) power sources. In our case there is a 12V - 5V stepdown converter powering the Pi and Arduino.

Below is the system schematic:

![System Schematic](resources/sykkeldelautomat_schem.png)

---

## Wiring and Pinouts

### Raspberry Pi ↔ I²C LCD

| Raspberry Pi Pin         | LCD I²C Backpack Pin |
| ------------------------ | -------------------- |
| 3.3V (Pin 1)             | VCC                  |
| GND (Pin 6)              | GND                  |
| GPIO 2 (Pin 3, SDA)      | SDA                  |
| GPIO 3 (Pin 5, SCL)      | SCL                  |

*Ensure I²C is enabled on the Raspberry Pi (via `raspi-config`). The typical I²C address is `0x27`.*

### Raspberry Pi ↔ 4×4 Matrix Keypad

| Raspberry Pi GPIO Pin | Keypad Pin (Function) |
| --------------------- | --------------------- |
| GPIO 21               | Pin 1 (Column 4)      |
| GPIO 20               | Pin 2 (Column 3)      |
| GPIO 16               | Pin 3 (Column 2)      |
| GPIO 12               | Pin 4 (Column 1)      |
| GPIO 1                | Pin 5 (Row 4)         |
| GPIO 7                | Pin 6 (Row 3)         |
| GPIO 8                | Pin 7 (Row 2)         |
| GPIO 25               | Pin 8 (Row 1)         |

*(Pin 1 is on the left when viewed from the front)*

### Arduino Mega 2560 ↔ Relay Boards

#### Relay Board 1 – Doors 1–16

| Arduino Pin | Relay Channel (Door) |
| ----------- | -------------------- |
| 23          | 1 (Door 1)           |
| 25          | 2 (Door 2)           |
| 27          | 3 (Door 3)           |
| 29          | 4 (Door 4)           |
| 31          | 5 (Door 5)           |
| 33          | 6 (Door 6)           |
| 35          | 7 (Door 7)           |
| 37          | 8 (Door 8)           |
| 39          | 9 (Door 9)           |
| 41          | 10 (Door 10)         |
| 43          | 11 (Door 11)         |
| 45          | 12 (Door 12)         |
| 47          | 13 (Door 13)         |
| 49          | 14 (Door 14)         |
| 51          | 15 (Door 15)         |
| 53          | 16 (Door 16)         |

#### Relay Board 2 – Doors 17–20

| Arduino Pin | Relay Channel (Door) |
| ----------- | -------------------- |
| 22          | 1 (Door 17)          |
| 24          | 2 (Door 18)          |
| 26          | 3 (Door 19)          |
| 28          | 4 (Door 20)          |
| 30          | 5                    |
| 32          | 6                    |
| 34          | 7                    |
| 36          | 8                    |
| 38          | 9                    |
| 40          | 10                   |
| 42          | 11                   |
| 44          | 12                   |
| 46          | 13                   |
| 48          | 14                   |
| 50          | 15                   |
| 52          | 16                   |

*Wiring Note:* Each relay channel's normally-open (NO) contact is wired in series with a 12V lock. We break the positive terminal of the locks power through the relay. When activated, the relay closes the circuit, supplying power to unlock the door.

Refer to the image below for a visual overview of the relay boards:

![Relay Boards](resources/relayboards.jpg)

And here’s an image of the finished installation:

![Finished Installation](resources/finished.jpg)

---

## Raspberry Pi Software

All software used on the Raspberry Pi is located in the `raspberrypi/` directory.

### order_service.py

- **Purpose:**  
  - Monitors keypad input.
  - Checks pickup codes against a local SQLite database.
  - Displays user feedback on LCD.
  - Sends serial commands to the Arduino (e.g., `OPEN:<door>:<wait>:<duration>`) to unlock doors.
- **Key Features:**  
  - **Initialization:** Sets up the I²C LCD and GPIO for the keypad.
  - **Database:** Uses SQLite to store order details (IDs, codes, door numbers).
  - **Background Threads:**  
    - *Orders Sync Loop:* Fetches new orders every 60 seconds.
    - *Offline Sync Loop:* Tries to syncs actions done without internet connectivity with the server every 5 minutes.
  - **Serial Communication:** Uses `/dev/ttyUSB0` or `/dev/ttyACM0` at 9600 baud.

### online_unlocks.py

- **Purpose:**  
  - Polls the API endpoint `get_door_requests.php` to retrieve remote unlock requests.
  - Sends commands to the Arduino to open the requested door.
  - Acknowledges the command execution via `mark_request_executed.php`.

### constantsTemplate.py

A configuration file template. Copy it to `constants.py` and modify the following:
- `API_URL` – Base URL of the API.
- `API_KEY` – Secret key for API authentication.
- `DB_FILE` – Path to the local SQLite database.
- `SERIAL_PORT` – Serial port (e.g., `/dev/ttyUSB0` or `/dev/ttyACM0`).
- `OPEN_ALL_CODE` – Master code for opening all doors.
- `ALL_DOORS` – List of all door numbers (default `[1, 2, …, 20]`).

### Test Scripts

Located in the `raspberrypi/test scripts/` directory:
- **test_keypad.py:** Validates keypad wiring and input.
- **test_lcd.py:** Checks LCD display functionality.
- **test_relay.py:** Tests relay activation via the Arduino.
- **test_camera.py:** (Optional) Tests camera and QR code functionality.

### Systemd Services

Two service files are provided for auto-start:
- **order_service.service:** Runs `order_service.py` on boot.
- **online_unlocks.service:** Runs `online_unlocks.py` on boot.

*Example commands to install and start the services:*

```bash
sudo cp /home/pi/felles-sykkeldelautomat/raspberrypi/online_unlocks.service /etc/systemd/system/
sudo cp /home/pi/felles-sykkeldelautomat/raspberrypi/order_service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable order_service.service
sudo systemctl enable online_unlocks.service
sudo systemctl start order_service.service
sudo systemctl start online_unlocks.service
````

# Website API and WooCommerce Integration

## WooCommerce Hooks `functions.php`

All software used on the website is located in the `website-api/` directory.

### Purpose:
- **Generate unique 4-character pickup and return codes:**  
  Using characters A–D and digits 0–9.
- **Assign codes to orders when payment completes:**  
  (via `woocommerce_payment_complete`).
- **For Bookly bookings:**  
  Assign opening codes based on matching product attributes.

### Door Attribute:
Each product in the vending machine must have a custom attribute `Door` (e.g., `Door = 7`).

## API Endpoints

### orders.php
Outputs JSON data for recent orders. The Raspberry Pi fetches this to update its local SQLite database.

### update_order_pickup.php
Updates an order with a pickup (or opening or return) timestamp after the door is opened.

### get_door_requests.php
Returns pending remote admin unlock requests.

### open_door.php
Allows admin-initiated door open commands via the web interface.

### mark_request_executed.php
Confirms a remote unlock request has been executed.

## Admin Web Interface

### Features:
- **Login-protected:**  
  Uses credentials defined in `constants.php`.
- **Dashboard:**  
  Displays door statuses and recent orders.
- **Remote unlock buttons:**  
  Provides buttons to trigger door opens.

### Database Table:
Create a custom table `sykkeldelautomat_onlinerequests` in your WordPress MySQL database:

```sql
CREATE TABLE IF NOT EXISTS `sykkeldelautomat_onlinerequests` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `door_number` INT NOT NULL,
  `command` VARCHAR(50) DEFAULT 'open',
  `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `executed` TINYINT(1) DEFAULT 0,
  PRIMARY KEY (`id`)
);
```

# Setup Guide

## 1. Hardware Assembly and Wiring

### Cabinet and Locks
- **Modify Cabinet:** Use an IKEA Kallax shelf as the cabinet.
- **Install Locks:** Mount 12V cabinet locks on each door.
- **Wiring:** Run wires from each lock to the electronics compartment.

### Mount Electronics
- **Relay Boards:** Install two 16-channel relay boards inside the cabinet.
- **Controllers:** Mount the Arduino Mega 2560 and the Raspberry Pi.

### Power Distribution
- **Power Supply:** Set up a 12V DC power supply for the locks.
- **Lock Wiring:** Wire each lock’s negative lead to the relay’s normally-open (NO) contact and connect the common (COM) to the 12V negative.

### Arduino to Relay Wiring
- **Digital Pins:** Connect Arduino digital pins:
  - Pins 23–53 for Relay Board 1.
  - Pins 22, 24, 26, 28 for Relay Board 2.
- **Power Connections:** Connect Arduino 5 V and GND to the relay boards.

### Raspberry Pi Wiring
- **I²C LCD:** Connect the I²C LCD to the Pi.
- **Keypad:** Wire the 4×4 keypad to the Pi’s GPIO according to the provided mapping.
- **USB Connection:** Connect the Arduino to the Pi via USB.

### Grounding
- **Common Ground:** Ensure all components share a common ground.

---

## 2. Raspberry Pi Software Setup

### Prepare the Pi
- **OS Installation:** Install Raspberry Pi OS and enable I²C (via `raspi-config`).

### Install System Packages
```bash
sudo apt-get update && sudo apt-get upgrade
sudo apt-get install python3-pip python3-venv git libzbar0 i2c-tools
```

### Clone the Repository
```bash
git clone https://github.com/your-repo/felles-sykkeldelautomat.git /home/pi/felles-sykkeldelautomat
```
### Set Up Python Environment
```bash
python3 -m venv /home/pi/.venv
source /home/pi/.venv/bin/activate
pip install -r /home/pi/felles-sykkeldelautomat/raspberrypi/requirements.txt
```
### Configure Constants
```bash
cp /home/pi/felles-sykkeldelautomat/raspberrypi/constantsTemplate.py /home/pi/felles-sykkeldelautomat/raspberrypi/constants.py
nano /home/pi/felles-sykkeldelautomat/raspberrypi/constants.py
```
- Edit values such as `API_URL`, `API_KEY`, `OPEN_ALL_CODE`, `SERIAL_PORT`, etc.

### Test Hardware
#### LCD Test:
```bash
python /home/pi/felles-sykkeldelautomat/raspberrypi/test\ scripts/test_lcd.py
```
#### Keypad Test:
```bash
python /home/pi/felles-sykkeldelautomat/raspberrypi/test\ scripts/test_keypad.py
```
#### Relay Test:
```bash
python /home/pi/felles-sykkeldelautomat/raspberrypi/test\ scripts/test_relay.py
```
#### (Optional) Camera/QR Code Test:
```bash
python /home/pi/felles-sykkeldelautomat/raspberrypi/test\ scripts/test_camera.py
```
### Install and Enable Services
- Follow the Raspberry Pi Software section above for setting up services.

## 3. Arduino Firmware Setup

### Install Arduino IDE
- Set up the Arduino IDE and select **Arduino Mega 2560**.

### Flash the Firmware
- Open `sykkeldelautomat.ino` from the `arduinomega/` folder and upload it.

### Test Serial Communication
- Use the Serial Monitor to send commands (e.g., `OPEN:1:0:5000`).

### Connect the Arduino to the Pi
- Ensure the Arduino is connected via USB for serial communication.

---

## 4. WooCommerce and Server Setup

### WooCommerce Product Setup
- **Product Category:** Create a product category for Sykkeldelautomat items (e.g., "Sykkeldelautomat").
- **Custom Attribute:** Assign each product a custom attribute "Door" with the appropriate number.

### Bookly Integration (Optional)
- Set up Bookly services and ensure they correctly map to WooCommerce products.

### WordPress Code Integration
- Add the provided functions from `website-api/functions.php` to your theme’s `functions.php` or as a custom plugin.

### Upload API Files
- Copy all PHP files from `website-api/` to your server (e.g., `yourdomain.com/api/`).

### Configure constants.php
- Update `constants.php` as needed.

### Database Table
- Create the `sykkeldelautomat_onlinerequests` table (refer to the provided SQL snippet).

### Configure WooCommerce Emails (Optional)
- Customize emails to include pickup instructions and codes.

---

## 5. Maintenance and Use

### Restocking
- Update product door attributes when adding new items.

### Monitoring
- Use the admin web interface to monitor door statuses and order pickups.

### Logs
- Check system logs using `journalctl` for troubleshooting.

### WooCommerce Integration
- Verify that order hooks assign codes correctly and that API endpoints are responsive.

---

By following this guide, you'll have a fully functional **Sykkeldelautomat** that integrates physical hardware with a WooCommerce store, enabling automated item pickups and remote door control.

**Enjoy your new automated pickup system!**
