import machine
import time
from pins import ENC_A
from pins import ENC_B
from pins import ENC_BTN
from pins import MODE_BTN

PU = machine.Pin.PULL_UP
IN = machine.Pin.IN

enc_a = machine.Pin(ENC_A, IN, PU)
enc_b = machine.Pin(ENC_B, IN, PU)
enc_btn = machine.Pin(
    ENC_BTN, IN, PU
)
mode_btn = machine.Pin(
    MODE_BTN, IN, PU
)

last_a = enc_a.value()
last_mode = 0

DOUBLE = 350
click_count = 0
last_click = 0
btn_was_down = False

def read():
    global last_a
    a = enc_a.value()
    b = enc_b.value()
    delta = 0
    if a != last_a:
        if a == 0:
            if b != a:
                delta = 1
            else:
                delta = -1
    last_a = a
    return delta

def get_clicks():
    global click_count
    global last_click
    global btn_was_down
    now = time.ticks_ms()
    pressed = enc_btn.value() == 0
    result = 0
    if pressed and not btn_was_down:
        gap = time.ticks_diff(
            now, last_click
        )
        if gap < DOUBLE:
            click_count += 1
        else:
            click_count = 1
        last_click = now
    if not pressed and btn_was_down:
        pass
    btn_was_down = pressed
    gap = time.ticks_diff(
        now, last_click
    )
    if (
        click_count > 0
        and not pressed
        and gap > DOUBLE
    ):
        result = click_count
        click_count = 0
    return result

def mode_clicked():
    global last_mode
    now = time.ticks_ms()
    if mode_btn.value() == 0:
        diff = time.ticks_diff(
            now, last_mode
        )
        if diff > 200:
            last_mode = now
            return True
    return False