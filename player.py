from machine import I2S, Pin
import _thread
import gc
import time

import sd_driver as sd
from pins import I2S_SCK, I2S_WS, I2S_SD


is_playing = False
volume = 15

IBUF_SIZE = 49_152
CHUNK_SIZE = 8192
BUFFER_COUNT = 4

_filename = None
_file = None
_i2s = None
_bytes_left_to_read = 0

_buffers = [bytearray(CHUNK_SIZE) for _ in range(BUFFER_COUNT)]
_views = [memoryview(buf) for buf in _buffers]
_lengths = [0 for _ in range(BUFFER_COUNT)]
_write_index = 0
_filled_count = 0

_thread_started = False
_lock = _thread.allocate_lock()

underruns = 0
min_free = 999999
memory_errors = 0


def _i2s_format(channels):
    if channels == 1:
        return I2S.MONO
    return I2S.STEREO


def _open_i2s(info):
    return I2S(
        0,
        sck=Pin(I2S_SCK),
        ws=Pin(I2S_WS),
        sd=Pin(I2S_SD),
        mode=I2S.TX,
        bits=info["bits_per_sample"],
        format=_i2s_format(info["channels"]),
        rate=info["sample_rate"],
        ibuf=IBUF_SIZE,
    )


def _reset_buffers():
    global _write_index, _filled_count
    _write_index = 0
    _filled_count = 0
    for i in range(BUFFER_COUNT):
        _lengths[i] = 0


def _close_current():
    global is_playing, _filename, _file, _i2s, _bytes_left_to_read

    is_playing = False
    _bytes_left_to_read = 0
    _reset_buffers()

    if _i2s is not None:
        _i2s.deinit()
        _i2s = None

    if _file is not None:
        _file.close()
        _file = None

    _filename = None


def _load(filename):
    global _filename, _file, _i2s, _bytes_left_to_read
    global underruns, min_free, memory_errors

    if filename is None:
        print("No song selected")
        return False

    underruns = 0
    min_free = gc.mem_free()
    memory_errors = 0

    info = sd.read_wav_info(filename)
    if info["audio_format"] != 1:
        raise ValueError("only PCM WAV files are supported")
    if info["data_offset"] is None:
        raise ValueError("WAV file has no data chunk")
    if (
        info["sample_rate"] != 48000
        or info["bits_per_sample"] != 16
        or info["channels"] != 2
    ):
        print("Warning: expected 48 kHz, 16-bit, stereo WAV")

    print("PLAY", filename)
    print(
        "WAV:",
        info["channels"],
        "ch",
        info["sample_rate"],
        "Hz",
        info["bits_per_sample"],
        "bit",
    )

    _file = sd.open_file(filename, "rb")
    _file.seek(info["data_offset"])
    _i2s = _open_i2s(info)
    _bytes_left_to_read = info["data_size"]
    _filename = filename
    _reset_buffers()
    return True


def _start_thread():
    global _thread_started
    if not _thread_started:
        _thread.start_new_thread(_audio_thread, ())
        _thread_started = True


def _fill_one_buffer():
    global _bytes_left_to_read, _filled_count, min_free, memory_errors

    _lock.acquire()
    try:
        if _file is None or _bytes_left_to_read <= 0:
            return False
        if _filled_count >= BUFFER_COUNT:
            return False

        file_obj = _file
        index = (_write_index + _filled_count) % BUFFER_COUNT
        max_read = CHUNK_SIZE
        if _bytes_left_to_read < max_read:
            max_read = _bytes_left_to_read
        if max_read == CHUNK_SIZE:
            read_view = _views[index]
        else:
            read_view = _views[index][:max_read]
    finally:
        _lock.release()

    free = gc.mem_free()
    if free < min_free:
        min_free = free

    try:
        n = file_obj.readinto(read_view)
    except MemoryError:
        memory_errors += 1
        gc.collect()
        n = file_obj.readinto(read_view)

    if n is None:
        n = max_read

    _lock.acquire()
    try:
        if file_obj is not _file:
            return False
        if n <= 0:
            _bytes_left_to_read = 0
            return False

        _lengths[index] = n
        _filled_count += 1
        _bytes_left_to_read -= n
        return True
    finally:
        _lock.release()


def play(filename):
    global is_playing

    _lock.acquire()
    try:
        _start_thread()
        same_file = filename == _filename and _file is not None
        if same_file:
            is_playing = True
            print("RESUME", filename)
            return

        _close_current()
        loaded = _load(filename)
    finally:
        _lock.release()

    if not loaded:
        return

    gc.collect()
    update(4)

    _lock.acquire()
    try:
        is_playing = True
    finally:
        _lock.release()


def pause():
    global is_playing
    _lock.acquire()
    try:
        is_playing = False
    finally:
        _lock.release()
    print("PAUSE")
    stats()


def stop():
    _lock.acquire()
    try:
        old_filename = _filename
        _close_current()
    finally:
        _lock.release()
    if old_filename is not None:
        print("STOP", old_filename)


def update(max_buffers=2):
    for _ in range(max_buffers):
        if not _fill_one_buffer():
            break


def _write_all(i2s_obj, view, length):
    written = 0
    while written < length:
        if written == 0 and length == CHUNK_SIZE:
            write_view = view
        else:
            write_view = view[written:length]

        count = i2s_obj.write(write_view)
        if count is None:
            count = length - written
        if count <= 0:
            time.sleep_ms(1)
        else:
            written += count


def _audio_thread():
    global _write_index, _filled_count, underruns

    while True:
        _lock.acquire()
        try:
            playing = is_playing
            i2s_obj = _i2s
            index = _write_index
            filled = _filled_count
            bytes_left = _bytes_left_to_read

            if playing and i2s_obj is not None and filled > 0:
                view = _views[index]
                length = _lengths[index]
            else:
                view = None
                length = 0
        finally:
            _lock.release()

        if not playing or i2s_obj is None:
            time.sleep_ms(5)
            continue

        if filled <= 0:
            if bytes_left <= 0:
                stop()
            else:
                underruns += 1
                time.sleep_ms(1)
            continue

        _write_all(i2s_obj, view, length)

        _lock.acquire()
        try:
            if i2s_obj is _i2s and _filled_count > 0:
                _lengths[_write_index] = 0
                _write_index = (_write_index + 1) % BUFFER_COUNT
                _filled_count -= 1
        finally:
            _lock.release()


def set_vol(vol):
    print("VOL", vol)


def stats():
    print(
        "underruns:",
        underruns,
        "min_free:",
        min_free,
        "mem_errors:",
        memory_errors,
        "filled:",
        _filled_count,
    )
