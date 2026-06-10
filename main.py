import time
import display
import encoder
import player
import songs

MC = 0
MS = 1
mode = MC
display_dirty = True
last_playing = False


def render_display():
    if mode == MC:
        display.control(
            songs.name(),
            player.is_playing,
            player.volume
        )
    else:
        display.songs(
            songs.song_list,
            songs.display_current()
        )


def mark_display_dirty():
    global display_dirty
    display_dirty = True

display.startup()
songs.startup()
time.sleep(2)

while True:
    if player.is_playing != last_playing:
        last_playing = player.is_playing
        mark_display_dirty()

    if player.is_playing:
        player.update(4)
    else:
        player.update(1)

    d = encoder.read()

    if d != 0:
        if mode == MC:
            v = player.volume + d
            v = max(0, min(30, v))
            if v != player.volume:
                player.volume = v
                player.set_vol(v)
                mark_display_dirty()
        else:
            if d > 0:
                songs.next()
            else:
                songs.prev()
            mark_display_dirty()

    clicks = encoder.get_clicks()

    if clicks == 3:
        songs.prev()
        player.play(songs.selected_file())
        mark_display_dirty()

    elif clicks == 2:
        songs.next()
        player.play(songs.selected_file())
        mark_display_dirty()

    elif clicks == 1:
        if mode == MC:
            if player.is_playing:
                player.pause()
            else:
                n = songs.selected_file()
                player.play(n)
            mark_display_dirty()
        else:
            mode = MC
            n = songs.selected_file()
            player.play(n)
            mark_display_dirty()

    if encoder.mode_clicked():
        if mode == MC:
            mode = MS
        else:
            mode = MC
        mark_display_dirty()

    if display_dirty:
        render_display()
        display_dirty = False

    if player.is_playing:
        player.update(4)
    else:
        player.update(1)

    if not player.is_playing:
        time.sleep_ms(5)
