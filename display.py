import machine
import ssd1306
from pins import I2C_SDA, I2C_SCL

i2c = machine.I2C(
    0,
    scl=machine.Pin(I2C_SCL),
    sda=machine.Pin(I2C_SDA),
    freq=400000
)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

def startup():
    oled.fill(0)
    oled.text("My Audio Player", 0, 20)
    oled.text("  Starting...  ", 0, 40)
    oled.show()

def control(song, playing, volume):
    oled.fill(0)
    oled.text("[VOL / PLAY]", 0, 0)
    oled.text(song[:16], 0, 16)
    if playing:
        oled.text(">> PLAYING", 0, 30)
    else:
        oled.text("|| PAUSED", 0, 30)
    oled.text("Vol:", 0, 46)
    bar = int((volume / 30) * 88)
    oled.fill_rect(40, 47, bar, 8, 1)
    oled.rect(40, 47, 88, 8, 1)
    oled.show()

def songs(song_list, current):
    oled.fill(0)
    oled.text("[SONG SELECT]", 0, 0)
    total = len(song_list)
    for offset in range(-1, 2):
        idx = current - 1 + offset
        if idx < 0 or idx >= total:
            continue
        y = 16 + (offset + 1) * 16
        pre = "> " if offset == 0 else "  "
        line = (pre + song_list[idx])[:16]
        oled.text(line, 0, y)
    hint = "{}/{}".format(current, total)
    oled.text(hint, 128 - len(hint) * 8, 56)
    oled.show()