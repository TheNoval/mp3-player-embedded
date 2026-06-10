import time
import display
import encoder
import player
import songs

MC = 0
MS = 1
mode = MC

display.startup()
time.sleep(2)

while True:
    d = encoder.read()

    if d != 0:
        if mode == MC:
            v = player.volume + d
            v = max(0, min(30, v))
            player.volume = v
            player.set_vol(v)
        else:
            if d > 0:
                songs.next()
            else:
                songs.prev()

    clicks = encoder.get_clicks()

    if clicks == 3:
        songs.prev()
        player.play(songs.current)

    elif clicks == 2:
        songs.next()
        player.play(songs.current)

    elif clicks == 1:
        if mode == MC:
            if player.is_playing:
                player.pause()
            else:
                n = songs.current
                player.play(n)
        else:
            mode = MC
            n = songs.current
            player.play(n)

    if encoder.mode_clicked():
        if mode == MC:
            mode = MS
        else:
            mode = MC

    if mode == MC:
        display.control(
            songs.name(),
            player.is_playing,
            player.volume
        )
    else:
        display.songs(
            songs.song_list,
            songs.current
        )

    time.sleep_ms(5)