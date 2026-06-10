import struct
from machine import I2S, Pin

SCLK_PIN = 6
LRCK_PIN = 7
SDIN_PIN = 9
IBUF_SIZE = 16_384


def parse_wav_header(f):
    riff = f.read(12)
    if riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    fmt = None
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            raise ValueError("no data chunk found")
        chunk_id, size = hdr[0:4], struct.unpack("<I", hdr[4:8])[0]
        if chunk_id == b"fmt ":
            data = f.read(size + (size & 1))
            _afmt, channels, rate, _br, _al, bits = struct.unpack("<HHIIHH", data[:16])
            fmt = (channels, rate, bits)
        elif chunk_id == b"data":
            return fmt, f.tell(), size
        else:
            f.seek(size + (size & 1), 1)


def play_wav(path):
    f = open(path, "rb")
    (channels, rate, bits), data_offset, data_len = parse_wav_header(f)
    print("WAV:", channels, "ch", rate, "Hz", bits, "bit")

    i2s = I2S(
        0,
        sck=Pin(SCLK_PIN),
        ws=Pin(LRCK_PIN),
        sd=Pin(SDIN_PIN),
        mode=I2S.TX,
        bits=bits,
        format=I2S.STEREO if channels == 2 else I2S.MONO,
        rate=rate,
        ibuf=IBUF_SIZE,
    )

    f.seek(data_offset)
    chunk = bytearray(2048)
    mv = memoryview(chunk)
    remaining = data_len
    try:
        while remaining > 0:
            n = f.readinto(mv)
            if n == 0:
                break
            if n > remaining:
                n = remaining
            i2s.write(mv[:n])
            remaining -= n
    finally:
        i2s.deinit()
        f.close()
    print("done")


if __name__ == "__main__":
    play_wav("/tone48.wav")