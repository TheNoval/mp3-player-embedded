"""
Name: Joseph Nguyen
Date: 3/31/2026
Filename: blink_leds.py
Description: This micropython script blinks a NeoPixel strip of 4 LEDs on and off every 1 second.
    GPIO 22 is connected to the input of a Neopixel strip of 4 LEDs.
"""

from machine import Pin, Timer
import time
import neopixel

led = Pin(22, Pin.OUT)
np = neopixel.NeoPixel(Pin(22), 4)  # Initialize NeoPixel on pin 4 with 8 LEDs
while True:
    led.value(1)  # Turn on the LED
    for i in range(4):
        np[i] = (10, 10, 10)  # Set each LED to white
    np.write()  # Update the NeoPixel strip
    time.sleep(0.2)  # Wait for 1 second

    led.value(0)  # Turn off the LED
    for i in range(4):
        np[i] = (0, 0, 0)  # Set each LED to blue
    np.write()  # Update the NeoPixel strip
    time.sleep(0.2)  # Wait for 1 second