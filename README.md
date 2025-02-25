# FELLES Sykkeldelautomat

### *Documentation is still Work in Progress*

## Overview
This repository contains the files and instructions needed to build your own **Sykkeldelautomat** (bike part vending machine) or to maintain the one at FELLES SykkelLab.

The Sykkeldelautomat is constructed from an IKEA Kallax shelf, modified with doors equipped with 12V cabinet locks. These locks are controlled by relay boards, which are driven by an Arduino Mega. The Arduino, in turn, is connected to a Raspberry Pi via USB Serial.

Items are ordered through the [BergenFellesverksted.no](https://bergenfellesverksted.no) WooCommerce online store. When an item belongs to the Sykkeldelautomat category, a pickup code is automatically sent to the buyer. Additionally, each item is assigned a door using a WooCommerce `attribute` formatted as `door = NN`.

## Online Setup
The online system handles the assignment of pickup codes and manages order data. Here’s how it works:

- **Pickup Code Assignment:**  
  - Orders in the Sykkeldelautomat category are automatically assigned a pickup code.
  - Equipment booked through Bookly in the SykkelLab service receives both pickup and delivery codes.

- **WordPress Integration:**  
  To enable these features, include the functions from `website-api/functions.php` in your WordPress `functions.php`.

- **API Communication:**  
  A custom API (code available in the `website-api` folder) facilitates communication between the Raspberry Pi and your website. It:
  - Retrieves new orders.
  - Reads pickup codes stored in the `wpia_postmeta` table.
  - Saves pickup confirmation dates sent from the Raspberry Pi.
  - Displays a login-protected table of orders and pickup times.

> **Important:** Ensure that the "Staff member" name in WooCommerce exactly matches the item name. The system uses these names to associate orders with the correct door (via the `door` attribute).

## Hardware Overview
The core hardware components include:

- **Raspberry Pi 3B+:**  
  - Runs all services and communicates with the online API.
  - Directly connects to an LCD module and a 4x4 keypad.
  - Interfaces with the Arduino Mega via USB Serial.

- **Arduino Mega 2560:**  
  - Receives commands from the Raspberry Pi over serial.
  - Controls the relay boards to activate the cabinet locks.

Below is the system schematic:

![System Schematic](resources/sykkeldelautomat_schem.png)

## Relay Boards & Pinout
The system features **two 16-channel relay boards** housed in the enclosure:

- **Relay Board 1 (Bottom of Enclosure):**  
  - **Door 1:** Arduino Mega pin 23  
  - **Door 2:** Arduino Mega pin 25  
  - **Door 3:** Arduino Mega pin 27  
  - *(and so on…)*

- **Relay Board 2 (Top of Enclosure):**  
  - **Door 17:** Arduino Mega pin 22  
  - **Door 18:** Arduino Mega pin 24  
  - **Door 19:** Arduino Mega pin 26  
  - **Door 20:** Arduino Mega pin 28  
  - **Unused Channels:** Arduino Mega pins 30-52 (even numbers)

Refer to the image below for a visual overview of the relay boards:

![Relay Boards](resources/relayboards.jpg)

And here’s an image of the finished installation:

![Finished Installation](resources/finished.jpg)
