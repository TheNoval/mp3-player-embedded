import sd_driver as sd

song_list = []
current = 0


def startup():
    global song_list, current

    if sd.card_present():
        sd.mount()
    else:
        print("No SD card detected")
        return

    song_list = [
        filename for filename in sd.list_files()
        if filename.lower().endswith(".wav")
    ]
    song_list.sort()
    current = 0
    print(song_list)


def next():
    global current
    if not song_list:
        return
    total = len(song_list)
    current = current + 1
    if current >= total:
        current = 0


def prev():
    global current
    if not song_list:
        return
    current = current - 1
    if current < 0:
        current = len(song_list) - 1


def display_current():
    if not song_list:
        return 0
    return current + 1


def name():
    if not song_list:
        return "No songs"
    return song_list[current]


def selected_file():
    if not song_list:
        return None
    return song_list[current]


def selected_wav_info():
    filename = selected_file()
    if filename is None:
        return None
    return sd.read_wav_info(filename)


def print_selected_wav_info():
    try:
        print(selected_wav_info())
    except Exception as e:
        print("WAV info failed:", type(e), e)


def read_selected_bytes():
    filename = selected_file()
    if filename is None:
        return b""
    return sd.read_bytes(filename)


def read_selected_audio_chunk(offset=0, size=1024):
    filename = selected_file()
    if filename is None:
        return b""

    info = sd.read_wav_info(filename)
    if info["data_offset"] is None:
        return b""

    with sd.open_file(filename, "rb") as f:
        f.seek(info["data_offset"] + offset)
        return f.read(size)


def test_selected_audio_chunk(offset=0, size=1024):
    try:
        data = read_selected_audio_chunk(offset, size)
        print("Read", len(data), "bytes from", selected_file())
        return data
    except Exception as e:
        print("Audio chunk read failed:", type(e), e)
        return b""
