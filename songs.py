song_list = [
    "0001 - Track 1",
    "0002 - Track 2",
    "0003 - Track 3",
    "0004 - Track 4",
    "0005 - Track 5",
]

current = 1

def next():
    global current
    total = len(song_list)
    current = min(total, current + 1)

def prev():
    global current
    current = max(1, current - 1)

def name():
    return song_list[current - 1]