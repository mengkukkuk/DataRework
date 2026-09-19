"""Registers the serial-store sync loop as a Windows Service via NSSM, so it
keeps running after the DataRework GUI is closed.

NSSM (nssm.exe, installed in System32) is itself the registered service binary
and handles the Service Control Manager protocol; it then supervises our plain
console program as a child process. That sidesteps the pywin32 approach, where
pythonservice.exe resolved the Python runtime through the interactive shell's
PATH/VIRTUAL_ENV and therefore failed to start under the LocalSystem account.

Called from main.py once the GUI is up. All failures are logged and swallowed
so a service problem never stops the app from running.
"""
import ctypes
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAME = "DataReworkSerialStoreSync"
DISPLAY_NAME = "DataRework Serial Store Sync"
DESCRIPTION = (
    "Keeps serial_store.used_serials in sync with staging_serial_data "
    "activate counts for the DataRework app."
)

NSSM = "nssm.exe"
_CREATE_NO_WINDOW = 0x08000000
_INSTALL_FLAG = "--install-service"


def _base_dir():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent


def _payload_command():
    """The program NSSM supervises: the frozen sync exe, or python + the script."""
    base = _base_dir()
    if getattr(sys, "frozen", False):
        return [str(base / "SerialStoreSync.exe")]
    return [sys.executable, str(base / "serial_store_aio.py")]


def _run(args):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )


def _run_nssm(*args):
    """Run an nssm command, raising with nssm's (UTF-16) message on failure."""
    proc = subprocess.run(
        [NSSM, *args],
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-16-le", errors="replace").strip()
        raise RuntimeError(f"nssm {args[0]} failed ({proc.returncode}): {detail}")
    return proc


def is_service_installed():
    return _run(["sc", "query", SERVICE_NAME]).returncode == 0


def is_service_running():
    proc = _run(["sc", "query", SERVICE_NAME])
    if proc.returncode != 0:
        return False
    match = re.search(r"STATE\s+:\s+\d+\s+(\w+)", proc.stdout)
    return bool(match) and match.group(1) == "RUNNING"


def service_binary_path():
    """The registered BINARY_PATH_NAME, or None when the service isn't installed."""
    proc = _run(["sc", "qc", SERVICE_NAME])
    if proc.returncode != 0:
        return None
    match = re.search(r"BINARY_PATH_NAME\s+:\s+(.+)", proc.stdout)
    return match.group(1).strip() if match else None


def _is_nssm_managed():
    path = service_binary_path()
    return bool(path) and "nssm" in path.lower()


def _is_elevated():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def install_service():
    """Register (or re-register) and start the service. Requires elevation.

    If the service exists but isn't NSSM-managed -- e.g. the earlier pywin32
    registration -- it is removed first so it can be replaced cleanly.
    """
    if is_service_installed() and not _is_nssm_managed():
        logger.info("Replacing non-NSSM registration of %s", SERVICE_NAME)
        _run_nssm("remove", SERVICE_NAME, "confirm")

    if not is_service_installed():
        program, *args = _payload_command()
        _run_nssm("install", SERVICE_NAME, program, *args)

        log_dir = _base_dir() / "logs"
        log_dir.mkdir(exist_ok=True)
        _run_nssm("set", SERVICE_NAME, "AppDirectory", str(_base_dir()))
        _run_nssm("set", SERVICE_NAME, "DisplayName", DISPLAY_NAME)
        _run_nssm("set", SERVICE_NAME, "Description", DESCRIPTION)
        _run_nssm("set", SERVICE_NAME, "Start", "SERVICE_AUTO_START")
        _run_nssm("set", SERVICE_NAME, "AppStdout", str(log_dir / "serial_store_sync.log"))
        _run_nssm("set", SERVICE_NAME, "AppStderr", str(log_dir / "serial_store_sync.log"))

    if not is_service_running():
        _run_nssm("start", SERVICE_NAME)


def _elevate_and_install():
    """Re-launch ourselves elevated to do the install (a single UAC prompt)."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, _INSTALL_FLAG
    else:
        exe = sys.executable
        params = f'"{Path(__file__).resolve()}" {_INSTALL_FLAG}'

    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0)
    if result <= 32:
        logger.warning(
            "Elevation for %s install was declined or failed (code %s)",
            SERVICE_NAME, result,
        )


def ensure_service_running():
    """Make sure the sync service is installed and running; never raises."""
    try:
        if is_service_running() and _is_nssm_managed():
            return
        if _is_elevated():
            install_service()
        else:
            _elevate_and_install()
    except Exception:
        logger.exception("Failed to ensure %s is running", SERVICE_NAME)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if _INSTALL_FLAG in sys.argv:
        install_service()
    else:
        ensure_service_running()
