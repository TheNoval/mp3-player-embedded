import machine
import time
from pins import ENC_A, ENC_B, ENC_BTN, MODE_BTN

IN = machine.Pin.IN

# No internal pull-ups: external resistors are present on the board.
# (Matches the working class-lab bring-up.)
enc_a = machine.Pin(ENC_A, IN)
enc_b = machine.Pin(ENC_B, IN)
enc_btn = machine.Pin(ENC_BTN, IN)
mode_btn = machine.Pin(MODE_BTN, IN)

# --- rotation: the lab's proven interrupt logic ----------------------------
# Interrupt on A only, both edges. Compare A and B for direction. This is the
# decoder from rotaryEncoder.py that already works on this hardware.
_counter = 0


def _encoder_cb(pin):
    # Keep allocation-free: can fire while playback has the GC disabled.
    global _counter
    if enc_a.value() == enc_b.value():
        _counter -= 1   # swap the -= and += if the direction is reversed
    else:
        _counter += 1


enc_a.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
          handler=_encoder_cb)


def read():
    """Net steps turned since the last call, then cleared."""
    global _counter
    d = _counter
    _counter = 0
    return d


# --- buttons: polled (slow, human-paced, so polling is reliable) -----------
DOUBLE = 350
click_count = 0
last_click = 0
btn_was_down = False
last_mode = 0


def get_clicks():
    global click_count, last_click, btn_was_down
    now = time.ticks_ms()
    pressed = enc_btn.value() == 0
    result = 0
    if pressed and not btn_was_down:
        gap = time.ticks_diff(now, last_click)
        if gap < DOUBLE:
            click_count += 1
        else:
            click_count = 1
        last_click = now
    btn_was_down = pressed
    gap = time.ticks_diff(now, last_click)
    if click_count > 0 and not pressed and gap > DOUBLE:
        result = click_count
        click_count = 0
    return result


def mode_clicked():
    global last_mode
    now = time.ticks_ms()
    if mode_btn.value() == 0:
        if time.ticks_diff(now, last_mode) > 200:
            last_mode = now
            return True
    return False