is_playing = False
volume     = 15

def play(track):
    global is_playing
    is_playing = True
    print("PLAY", track)

def pause():
    global is_playing
    is_playing = False
    print("PAUSE")

def set_vol(vol):
    print("VOL", vol)