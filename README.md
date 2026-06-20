# Aurora Player

A fast, lightweight desktop media player built with **PySide6 (Qt6)** and **libVLC**,
with a classic VLC-style interface: a full menu bar, a video canvas, a transport bar,
and a togglable side panel for the playlist, media library, history and favorites.

## Features

- Plays common video (MP4, MKV, AVI, MOV, FLV, WMV, WebM, MPEG, 3GP, TS) and audio
  (MP3, AAC, WAV, FLAC, OGG, M4A) formats via libVLC
- Subtitle support (SRT/ASS/SSA/VTT) with delay adjustment and auto-loading of sidecar files
- Audio/subtitle track selection, audio delay
- Aspect ratio, crop, rotate, mirror, zoom, color adjustments (brightness/contrast/gamma/hue/saturation)
- 10-band equalizer
- Playback speed (0.25x–3x), frame-by-frame stepping, A→B clip recording (needs `ffmpeg`)
- Snapshots, bookmarks, resume playback, playback history, favorites
- Playlist with drag-and-drop reordering, repeat (one/all), shuffle, M3U import/export
- Media library scanning, search, network stream / URL playback
- Picture-in-Picture, mini player, always-on-top, sleep timer
- Dark theme, configurable accent color, keyboard shortcuts

## Requirements

- Python 3.10+
- [VLC media player](https://www.videolan.org/) installed (64-bit, matching your Python architecture)
- `ffmpeg` on PATH (optional — only for the clip recording feature)

## Install & Run

```bash
pip install -r requirements.txt
python main.py
```

## Project Structure

```
video_player/
├── main.py                 # entry point
├── player.py               # backend composition root
├── backend/                # model layer (no UI)
│   ├── vlc_engine.py       # libVLC wrapper
│   ├── playlist_manager.py
│   ├── subtitle_manager.py
│   ├── history_manager.py
│   ├── settings_manager.py
│   └── database.py         # SQLite
├── ui/                     # view layer
│   ├── main_window.py      # QMainWindow + menu bar (controller)
│   ├── controls.py         # transport bar
│   ├── playlist.py
│   ├── dialogs.py
│   └── settings.py
├── assets/icons/           # app icon
└── styles/dark_theme.qss
```

## License

MIT
