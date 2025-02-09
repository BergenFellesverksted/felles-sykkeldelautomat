# FELLES Sykkeldelautomat
### This is still very much a work in progress...
## Introduction
This repository contains files and instructions to create your own Sykkeldelautomat. Or do mainteinanse on the one at FELLES SykkelLab.

The Sykkeldelautomat (bike part wending machine) is a IKEA Kallax shelf with doors for each opening, operated by 12V cabinet locks. These are operated by relay boards controlled by a Arduino Mega which again is controlled over Serial USB by a Raspberry Pi.

The items are ordered through the Woocommerce online store at BergenFellesverksted.no. If any of the items are in the Sykkeldelautomat category, a pickup code is automatically sent to the buyer.

The items are assigned a door in the system through the online Woocommerce, where you can add an `attribute` called `door = NN` to each item.

## Online setup
The orders get assigned a pickup code through Woocommerce. This section assigns pickup codes to the items in the store category Sykkeldelautomat, and pickup and delivery codes to equipment booked through Bookly in the service SykkelLab. To add this functunality, add the functions from `website-api/functions.php` to your WordPress `functions.php`.

One then need a API working on the website. The Raspberry Pi communicates with this API to get new orders. The code for the API is availiable in the `website-api` folder.

The API reads pickup codes added to the `wpia_postmeta` table and provides them to the Raspberry Pi. It then also saves pickup confirmed dates sent from the Raspberry Pi. Lastly it creates a table behind a login that shows the orders and the pickup times. 

Its important to make the name of the "Staff member" and the Item in the store the same, since the scripts use the names to match it and to find the `door` variable for the Bookly orders.