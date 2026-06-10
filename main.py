import time
import display
import encoder
import player
import songs


MODE_CONTROL = 0
MODE_SONGS = 1

PLAYING_DISPLAY_UPDATE_MS = 250

mode = MODE_CONTROL
display_dirty = True
last_display_update = 0
last_playing = False


def mark_display_dirty():
    global display_dirty
    display_dirty = True


def play_selected():
    player.play(songs.selected_file())
    mark_display_dirty()


def change_song(direction):
    if direction > 0:
        songs.next()
    else:
        songs.prev()
    mark_display_dirty()


def render_display():
    if mode == MODE_CONTROL:
        display.control(songs.name(), player.is_playing, player.volume)
    else:
        display.songs(songs.song_list, songs.display_current())


def maybe_render():
    global display_dirty, last_display_update

    if not display_dirty:
        return

    if player.is_playing:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_display_update) < PLAYING_DISPLAY_UPDATE_MS:
            return
        last_display_update = now

    render_display()
    display_dirty = False


def handle_encoder():
    d = encoder.read()
    if d == 0:
        return

    if mode == MODE_CONTROL:
        v = max(0, min(30, player.volume + d))
        if v != player.volume:
            player.volume = v
            player.set_vol(v)
            mark_display_dirty()
    else:
        change_song(d)


def handle_clicks():
    global mode

    clicks = encoder.get_clicks()
    if clicks == 3:
        change_song(-1)
        play_selected()
    elif clicks == 2:
        change_song(1)
        play_selected()
    elif clicks == 1:
        if mode == MODE_CONTROL:
            if player.is_playing:
                player.pause()
                mark_display_dirty()
            else:
                play_selected()
        else:
            mode = MODE_CONTROL
            play_selected()


def handle_mode_button():
    global mode

    if not encoder.mode_clicked():
        return

    if mode == MODE_CONTROL:
        mode = MODE_SONGS
    else:
        mode = MODE_CONTROL
    mark_display_dirty()


def track_play_state():
    global last_playing

    if player.is_playing != last_playing:
        last_playing = player.is_playing
        mark_display_dirty()


display.startup()
songs.startup()
time.sleep(2)

while True:
    track_play_state()
    handle_encoder()
    
    player.update(2)

    handle_clicks()
    handle_mode_button()
    maybe_render()

    player.update(2)

    if not player.is_playing:
        time.sleep_ms(5)
