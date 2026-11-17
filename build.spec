# PyInstaller spec file for YouTube Downloader.
#
# Build with:
#   pyinstaller build.spec
#
# The resulting YouTubeDownloader.exe (Windows) is placed in dist/YouTubeDownloader/.
# To bundle FFmpeg, put ffmpeg.exe (and ffprobe.exe) in a "ffmpeg" folder next to
# this spec file before building -- see the "FFmpeg Distribution" section of README.md.

import os

block_cipher = None

project_root = os.path.abspath(os.path.dirname(os.path.abspath(SPEC)))
ffmpeg_dir = os.path.join(project_root, "ffmpeg")

datas = []
if os.path.isdir(ffmpeg_dir):
    for name in os.listdir(ffmpeg_dir):
        full_path = os.path.join(ffmpeg_dir, name)
        if os.path.isfile(full_path):
            datas.append((full_path, "ffmpeg"))

a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YouTubeDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, "assets", "app_icon.ico")
    if os.path.isfile(os.path.join(project_root, "assets", "app_icon.ico"))
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YouTubeDownloader",
)
