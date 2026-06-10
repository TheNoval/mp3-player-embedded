# mp3-player-embedded
An mp3 player made for a prototype board

## Files Needed

| File                       | What It Does                                        |
| -------------------------- | --------------------------------------------------- |
| `audio_player_frontend.py` | Main program (this is the file you run)             |
| `ssd1306.py`               | OLED display driver (must be uploaded to the board) |

## Setup

1. Connect the board to your computer using a USB cable.
2. Open VS Code and connect to the board using MicroPico.
3. Upload both files to the board.
4. Run `audio_player_frontend.py`.

## Hardware Connections

| Signal                | GPIO |
| --------------------- | ---- |
| OLED SDA              | 12   |
| OLED SCL              | 13   |
| Encoder A (ANG_A)     | 18   |
| Encoder B (ANG_B)     | 17   |
| Encoder Button (SW_C) | 5    |
| Mode Button (BTN)     | 21   |

## How to Use It

### Volume/Play Mode

* Turn the encoder to change the volume (0–30).
* Press the encoder to play or pause the song.
* Press the mode button to switch to Song Select mode.

### Song Select Mode

* Turn the encoder to move through the song list.
* Press the encoder to select and play a song.
* Press the mode button to go back to Volume/Play mode.

## Adding Songs

To add songs, update the `song_list` in `audio_player_frontend.py` so it matches the files on your SD card. The DFPlayer Mini expects song names like:

* `0001.mp3`
* `0002.mp3`
* `0003.mp3`

and so on.

## Next Step

Right now, the functions `dfplayer_play()`, `dfplayer_pause()`, and `dfplayer_set_volume()` only print messages for testing. After connecting the DFPlayer Mini, these functions should be replaced with the correct UART commands so the player can control the music.
