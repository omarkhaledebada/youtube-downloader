# YouTube Downloader

A desktop application for downloading YouTube videos, built with Python,
PySide6 (Qt), yt-dlp, and FFmpeg.

Paste a link, analyze it, pick a quality, and download — video and audio
are fetched and merged automatically when needed, with a live progress
view and a local download history.

> This tool only downloads content the user is authorized to download and
> does not attempt to bypass DRM, private-video restrictions, paywalls, or
> any other access control. Please respect YouTube's Terms of Service and
> applicable copyright law.

## Features

- Paste or type a YouTube URL and analyze it before downloading.
- Clean, simplified quality list (Best Quality, 2160p, 1440p, 1080p, 720p,
  480p, Audio Only) built from yt-dlp's raw format list, with an
  "Advanced Formats" view for the full raw list.
- Expected file size shown for every option, computed from yt-dlp's real
  size metadata (exact when available, `~approximate` otherwise, never
  invented).
- Automatic video+audio merging via FFmpeg when YouTube serves them as
  separate streams — the user only ever sees one final file.
- Optional MP3 conversion for Audio Only downloads, with selectable bitrate.
- Live progress: percentage, downloaded/total size, speed, ETA, and
  distinct phases ("Downloading video...", "Downloading audio...",
  "Merging video and audio...").
- Cancel button that stops downloads cleanly.
- Persistent settings (default download folder, default quality/format,
  audio quality, theme, window position) via `QSettings`.
- Local download history (SQLite) with Open File / Open Folder / Remove.
- Light and dark themes.
- All network/download/merge work runs off the UI thread (QThread +
  worker objects), so the interface never freezes.

## Development

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (cmd.exe): `.venv\Scripts\activate.bat`
- macOS/Linux: `source .venv/bin/activate`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python main.py
```

## Requirements

- **Python 3.10+**
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — extracts video metadata
  and performs the actual download. Installed via `requirements.txt`.
- **[FFmpeg](https://ffmpeg.org/)** — required to merge separately-served
  video and audio streams into one file, and to convert audio to MP3.
  FFmpeg is **not** installed via pip; see "FFmpeg Distribution" below.
  If FFmpeg is missing, the app will still run and can download formats
  that don't need merging or conversion; it will show a clear error for
  anything that does.

## Project Structure

```text
youtube-downloader/
│
├── main.py                  Application entry point (logging, exception
│                             hook, theme, QApplication, MainWindow)
├── requirements.txt
├── README.md
├── build.spec                PyInstaller build configuration
│
├── app/
│   ├── ui/                  All PySide6 widgets and dialogs
│   │   ├── main_window.py   Main window; wires the UI to the services
│   │   ├── settings_dialog.py
│   │   ├── history_dialog.py
│   │   ├── styles.py        Light/dark QSS stylesheets
│   │   └── widgets/         Reusable sub-widgets (video info, quality
│   │                        list, progress display)
│   │
│   ├── services/            Business logic, independent of the UI
│   │   ├── ytdlp_service.py       Metadata extraction (analysis)
│   │   ├── analysis_worker.py     QThread wrapper for analysis
│   │   ├── format_processor.py    Raw formats -> simplified choices
│   │   ├── download_service.py    QThread download/merge/convert worker
│   │   ├── ffmpeg_service.py      FFmpeg availability checks
│   │   ├── history_service.py     SQLite-backed download history
│   │   ├── error_mapping.py       Raw errors -> user-friendly messages
│   │   └── exceptions.py          Typed application exceptions
│   │
│   ├── models/               Plain data classes (VideoInfo, FormatOption,
│   │                         QualityChoice)
│   │
│   ├── utils/                 Formatting, validation, filename
│   │                         sanitization, FFmpeg lookup, logging
│   │
│   └── config/
│       └── settings.py       QSettings-backed persistent preferences
│
└── assets/                    Icons (optional; add app_icon.ico here for
                                a custom app/exe icon)
```

## Build a Windows .exe

This project uses [PyInstaller](https://pyinstaller.org/) to produce a
double-clickable `YouTubeDownloader.exe` that opens without a terminal
window.

1. Install PyInstaller inside your virtual environment:

   ```bash
   pip install pyinstaller
   ```

2. (Recommended) Place `ffmpeg.exe` in a folder named `ffmpeg` at the
   project root — see "FFmpeg Distribution" below. PyInstaller will bundle
   anything found there automatically.

3. Build:

   ```bash
   pyinstaller build.spec
   ```

4. The finished app is in `dist/YouTubeDownloader/`, with
   `YouTubeDownloader.exe` at its root. Copy or zip the whole
   `YouTubeDownloader` folder — it contains everything the exe needs
   (the Python runtime, Qt libraries, and bundled FFmpeg if you added it).

If you don't have a `build.spec` change to make, you can also build with a
single command instead of the spec file:

```bash
pyinstaller --noconsole --name YouTubeDownloader --add-data "ffmpeg;ffmpeg" main.py
```

(Omit `--add-data` if you are not bundling FFmpeg.)

## FFmpeg Distribution

The recommended approach for an end-user-friendly Windows build is to
**bundle `ffmpeg.exe` (and optionally `ffprobe.exe`) with the application**
so users never have to install anything themselves:

1. Download a Windows FFmpeg build (e.g. from
   [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or
   [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)).
2. Copy `ffmpeg.exe` (and `ffprobe.exe`, optional) into a folder named
   `ffmpeg` at the project root (`youtube-downloader/ffmpeg/ffmpeg.exe`).
3. Build with PyInstaller as shown above — the spec file automatically
   includes everything in that `ffmpeg` folder into the packaged app under
   `dist/YouTubeDownloader/ffmpeg/`.

At runtime, `app/utils/ffmpeg_locator.py` looks for FFmpeg in this order:

1. An `ffmpeg` folder next to the running executable (bundled case).
2. The same directory as the executable.
3. The system `PATH` (so a user-installed FFmpeg also works).

If FFmpeg cannot be found anywhere, the app does not crash — it shows a
clear message explaining that FFmpeg is required for the requested
operation (merging separate video/audio streams, or converting to MP3).

## Notes on Behavior

- yt-dlp often serves high resolutions (1440p, 2160p, and sometimes 1080p)
  as separate video-only and audio-only streams. The app detects this
  automatically and merges them with FFmpeg after downloading — the user
  is only ever shown and given one final file.
- File sizes shown before downloading use yt-dlp's `filesize` field when
  present, `filesize_approx` otherwise (shown as `~size`), or `Unknown`
  when neither is available. No size is ever fabricated.
- Downloaded filenames are derived from the video title, sanitized for
  Windows (`<>:"/\|?*` and control characters removed/replaced), and made
  unique automatically (`Title (1).mp4`, `Title (2).mp4`, ...) rather than
  silently overwriting existing files.
- All logs are written to a rotating log file under
  `%LOCALAPPDATA%\YouTubeDownloader\logs\app.log` on Windows (or
  `~/.youtube_downloader/logs/app.log` elsewhere), which is useful for
  diagnosing issues without a visible console window.
