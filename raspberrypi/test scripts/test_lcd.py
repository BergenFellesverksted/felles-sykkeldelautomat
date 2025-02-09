from time import sleep
from RPLCD.i2c import CharLCD

# Initialize for a 16x2 or 20x2 display
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)

lcd.backlight_enabled = True
lcd.clear()
sleep(0.5)

# Test writing on different lines
lcd.cursor_pos = (0, 0)  # First line
lcd.write_string("First Line Test")

lcd.cursor_pos = (1, 0)  # Second line
lcd.write_string("Second Line Test")

sleep(10)

lcd.backlight_enabled = False
lcd.clear()
