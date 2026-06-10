from machine import I2S, Pin
from array import array
import math
import time

SCLK_PIN = 6
LRCK_PIN = 7
MCLK_PIN = 8
SDIN_PIN = 9

SAMPLE_RATE = 48_000
MCLK_HZ = 24_576_000

BITS = 16
TONE_FREQ = 440
AMPLITUDE = 5000
BUFFER_FRAMES = 480
IBUF_SIZE = int(16_384)
PLAY_DURATION_MS = 100_000


def configure_clocks_and_i2s():
    i2s = I2S(
        0,
        sck=Pin(SCLK_PIN),
        ws=Pin(LRCK_PIN),
        sd=Pin(SDIN_PIN),
        mode=I2S.TX,
        bits=BITS,
        format=I2S.STEREO,
        rate=SAMPLE_RATE,
        ibuf=IBUF_SIZE,
    )
    return i2s


def generate_sine_buffer(sample_rate, frames=BUFFER_FRAMES):
    buf = array("h")
    two_pi = 2.0 * math.pi
    phase_step = two_pi * TONE_FREQ / sample_rate
    phase = 0.0

    for _ in range(frames):
        sample = int(AMPLITUDE * math.sin(phase))
        phase += phase_step
        if phase >= two_pi:
            phase -= two_pi

        # stereo interleaved: L, R
        buf.append(sample)
        buf.append(sample)

    return buf


def main():
    i2s = configure_clocks_and_i2s()
    audio = generate_sine_buffer(SAMPLE_RATE)
    start = time.ticks_ms()

    print("running")
    try:
        while time.ticks_diff(time.ticks_ms(), start) < PLAY_DURATION_MS:
            i2s.write(audio)
    finally:
        i2s.deinit()
    
    print("done")


if __name__ == "__main__":
    main()
