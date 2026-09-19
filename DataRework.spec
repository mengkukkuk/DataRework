# PyInstaller spec: builds two one-file exes.
#   DataRework.exe      - the PySide6 GUI (main.py), windowed, with the "R" icon.
#   SerialStoreSync.exe - the sync loop (serial_store_aio.py) as a plain console
#                         program; NSSM supervises it as the Windows Service, so
#                         it needs no service framework of its own.
#
# .env IS bundled into both exes, so the deployed dist/ folder contains no
# plaintext credentials file. Note this is obfuscation, not encryption: the
# onefile archive can be unpacked (e.g. pyinstxtractor) to recover .env. Treat
# the exes themselves as secrets -- never commit or publish them.
#
# Build with build.ps1, not pyinstaller directly: the running sync service holds
# an open handle on dist/SerialStoreSync.exe and PyInstaller cannot overwrite it
# (WinError 5), so the service has to be stopped first.

block_cipher = None

gui_a = Analysis(
    ['main.py'],
    pathex=[],
    # app_icon.ico is needed twice: bundled here so main.py can load it at
    # runtime (title bar / taskbar), and passed to EXE() below to embed it as
    # the file's Explorer icon.
    datas=[('style.css', '.'), ('assets/app_icon.ico', 'assets'), ('.env', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
gui_pyz = PYZ(gui_a.pure)
gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name='DataRework',
    console=False,
    icon='assets/app_icon.ico',
)

sync_a = Analysis(
    ['serial_store_aio.py'],
    pathex=[],
    datas=[('.env', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
sync_pyz = PYZ(sync_a.pure)
sync_exe = EXE(
    sync_pyz,
    sync_a.scripts,
    sync_a.binaries,
    sync_a.datas,
    [],
    name='SerialStoreSync',
    console=True,
)
