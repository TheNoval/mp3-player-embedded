from machine import I2S, Pin
import _thread
import gc
import time

import sd_driver as sd
from pins import I2S_SCK, I2S_WS, I2S_SD


# Public playback state ------------------------------------------------------

is_playing = False
volume = 15


# Audio/buffer tuning --------------------------------------------------------

IBUF_SIZE = 49_152
CHUNK_SIZE = 8192
BUFFER_COUNT = 4
GC_LOW_WATER = 8192


# Stream state ---------------------------------------------------------------

_filename = None
_pending_filename = None
_loading = False
_file = None
_i2s = None
_info = None
_bytes_left_to_read = 0


# Ring buffer state ----------------------------------------------------------

_buffers = [bytearray(CHUNK_SIZE) for _ in range(BUFFER_COUNT)]
_views = [memoryview(buf) for buf in _buffers]
_lengths = [0 for _ in range(BUFFER_COUNT)]

_read_index = 0
_write_index = 0
_filled_count = 0
_reserved_count = 0
_stream_id = 0


# Thread/debug state ---------------------------------------------------------

_thread_started = False
_lock = _thread.allocate_lock()

underruns = 0
min_free = 999999
memory_errors = 0


# Public API -----------------------------------------------------------------

def play(filename):
    """Start a new file, or resume the current file if it is already open."""
    global is_playing, _i2s, _pending_filename

    _lock.acquire()
    try:
        _start_thread()

        if filename == _filename and _file is not None:
            if _i2s is None and _info is not None:
                _i2s = _open_i2s(_info)
            resume_current = True
        else:
            _pending_filename = filename
            is_playing = False
            resume_current = False
    finally:
        _lock.release()

    if resume_current:
        update(4)
        _set_playing(True)
        print("RESUME", filename)


def pause():
    _set_playing(False)
    print("PAUSE")
    gc.collect()
    stats()


def stop():
    global _pending_filename

    _lock.acquire()
    try:
        _pending_filename = None
        old_filename = _filename
        _close_current()
    finally:
        _lock.release()

    if old_filename is not None:
        print("STOP", old_filename)
    gc.collect()


def update(max_buffers=2):
    """Fill up to max_buffers empty audio buffers from the SD card."""
    for _ in range(max_buffers):
        if _pending_filename is not None or _loading:
            break
        if _reserved_count > 0:
            break
        if not _fill_one_buffer():
            break


def set_vol(vol):
    global volume
    volume = max(0, min(30, vol))


def stats():
    print(
        "underruns:",
        underruns,
        "min_free:",
        min_free,
        "current_free:",
        gc.mem_free(),
        "mem_errors:",
        memory_errors,
        "filled:",
        _filled_count,
        "reserved:",
        _reserved_count,
    )


# Stream setup/teardown ------------------------------------------------------

def _set_playing(value):
    global is_playing
    _lock.acquire()
    try:
        is_playing = value
    finally:
        _lock.release()


def _start_thread():
    global _thread_started
    if not _thread_started:
        _thread.start_new_thread(_audio_thread, ())
        _thread_started = True


def _load(filename):
    global _filename, _file, _i2s, _info, _bytes_left_to_read
    global underruns, min_free, memory_errors

    if filename is None:
        print("No song selected")
        return False

    gc.collect()
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
    _info = info
    _bytes_left_to_read = info["data_size"]
    _filename = filename
    _reset_buffers()
    return True


def _close_current():
    global is_playing, _filename, _file, _i2s, _info, _bytes_left_to_read

    is_playing = False
    _bytes_left_to_read = 0
    _reset_buffers()
    _close_i2s()

    if _file is not None:
        _file.close()
        _file = None

    _filename = None
    _info = None


def _close_i2s():
    global _i2s
    if _i2s is not None:
        _i2s.deinit()
        _i2s = None


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


def _i2s_format(channels):
    if channels == 1:
        return I2S.MONO
    return I2S.STEREO


# Buffer producer ------------------------------------------------------------

def _reset_buffers():
    global _read_index, _write_index, _filled_count, _reserved_count, _stream_id

    _stream_id += 1
    _read_index = 0
    _write_index = 0
    _filled_count = 0
    _reserved_count = 0

    for i in range(BUFFER_COUNT):
        _lengths[i] = 0


def _fill_one_buffer():
    global _bytes_left_to_read, _write_index
    global _filled_count, _reserved_count, min_free, memory_errors

    reserved = _reserve_write_slot()
    if reserved is None:
        return False

    file_obj, stream_id, index, read_view, max_read = reserved
    _collect_if_safe()

    try:
        n = file_obj.readinto(read_view)
    except MemoryError:
        memory_errors += 1
        gc.collect()
        n = file_obj.readinto(read_view)

    if n is None:
        n = max_read

    return _commit_filled_buffer(file_obj, stream_id, index, n)


def _reserve_write_slot():
    global _write_index, _reserved_count

    _lock.acquire()
    try:
        if _file is None or _bytes_left_to_read <= 0:
            return None
        if _filled_count + _reserved_count >= BUFFER_COUNT:
            return None

        index = _write_index
        _write_index = (_write_index + 1) % BUFFER_COUNT
        _reserved_count += 1

        max_read = CHUNK_SIZE
        if _bytes_left_to_read < max_read:
            max_read = _bytes_left_to_read

        if max_read == CHUNK_SIZE:
            read_view = _views[index]
        else:
            read_view = _views[index][:max_read]

        return _file, _stream_id, index, read_view, max_read
    finally:
        _lock.release()


def _commit_filled_buffer(file_obj, stream_id, index, length):
    global _bytes_left_to_read, _filled_count, _reserved_count

    _lock.acquire()
    try:
        if file_obj is not _file or stream_id != _stream_id:
            _reserved_count -= 1
            return False
        if length <= 0:
            _reserved_count -= 1
            _bytes_left_to_read = 0
            return False

        _lengths[index] = length
        _reserved_count -= 1
        _filled_count += 1
        _bytes_left_to_read -= length
        return True
    finally:
        _lock.release()


def _collect_if_safe():
    free = _track_free_memory()
    if _filled_count >= 3 and free < GC_LOW_WATER:
        gc.collect()
        _track_free_memory()


def _track_free_memory():
    global min_free
    free = gc.mem_free()
    if free < min_free:
        min_free = free
    return free


# Audio consumer thread ------------------------------------------------------

def _audio_thread():
    global is_playing, _pending_filename
    global _read_index, _filled_count, underruns

    while True:
        pending, playing, i2s_obj, index, filled, bytes_left = _snapshot_state()

        if pending is not None:
            _handle_pending_file(pending)
            continue

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

        _write_all(i2s_obj, _views[index], _lengths[index])
        _consume_buffer(i2s_obj)


def _snapshot_state():
    global _pending_filename

    _lock.acquire()
    try:
        pending = _pending_filename
        if pending is not None:
            _pending_filename = None

        return (
            pending,
            is_playing,
            _i2s,
            _read_index,
            _filled_count,
            _bytes_left_to_read,
        )
    finally:
        _lock.release()


def _handle_pending_file(filename):
    global _loading

    _lock.acquire()
    try:
        _loading = True
        _close_current()
    finally:
        _lock.release()

    gc.collect()

    try:
        loaded = _load(filename)
    except Exception as e:
        print("PLAY failed:", type(e), e)
        loaded = False

    if loaded:
        update(4)
        _set_playing(True)

    _lock.acquire()
    try:
        _loading = False
    finally:
        _lock.release()


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


def _consume_buffer(i2s_obj):
    global _read_index, _filled_count

    _lock.acquire()
    try:
        if i2s_obj is _i2s and _filled_count > 0:
            _lengths[_read_index] = 0
            _read_index = (_read_index + 1) % BUFFER_COUNT
            _filled_count -= 1
    finally:
        _lock.release()
