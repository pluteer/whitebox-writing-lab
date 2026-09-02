from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


API_PORT = int(os.getenv("WHITEBOX_API_PORT", "8001"))
API_URL = f"http://127.0.0.1:{API_PORT}"


def portable_root() -> Path:
    executable_dir = Path(sys.executable).resolve().parent
    return executable_dir if (executable_dir / "runtime").is_dir() else Path(__file__).resolve().parents[1]


def paths(root: Path) -> dict[str, Path]:
    return {
        "api": root / "runtime" / "api" / "whitebox-api.exe",
        "data": root / "data",
        "projects": root / "data" / "projects",
        "secrets": root / "data" / "provider-secrets.json",
        "logs": root / "logs",
        "state": root / "runtime" / "api.pid.json",
        "version": root / "version.json",
        "web": root / "runtime" / "web",
    }


def show_error(message: str, no_dialog: bool = False) -> None:
    if os.name == "nt" and not no_dialog:
        ctypes.windll.user32.MessageBoxW(None, message, "Whitebox Writing", 0x10)
    else:
        print(message, file=sys.stderr)


def request_json(url: str, token: str | None = None, timeout: float = 2) -> dict:
    headers = {"X-Whitebox-Instance-Token": token} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return json.load(response)


def port_in_use() -> bool:
    with socket.socket() as client:
        client.settimeout(0.5)
        return client.connect_ex(("127.0.0.1", API_PORT)) == 0


def read_state(path: Path) -> dict | None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if set(state) != {"pid", "executable_path", "instance_token", "started_at"}:
            return None
        if not isinstance(state["pid"], int) or state["pid"] < 1:
            return None
        if not isinstance(state["instance_token"], str) or len(state["instance_token"]) != 64:
            return None
        if any(character not in "0123456789abcdef" for character in state["instance_token"]):
            return None
        if not Path(state["executable_path"]).is_absolute():
            return None
        if not isinstance(state["started_at"], int) or state["started_at"] < 1:
            return None
        return state
    except (OSError, ValueError, TypeError):
        return None


def process_image(pid: int) -> Path | None:
    if os.name != "nt":
        return None
    query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return None
    try:
        capacity = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return None
        return Path(buffer.value).resolve()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def process_started_at(pid: int) -> int | None:
    if os.name != "nt":
        return None
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return creation.value
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def state_owns_api(state: dict | None, api_path: Path) -> bool:
    if not state:
        return False
    actual = process_image(state["pid"])
    return bool(
        actual
        and os.path.normcase(actual) == os.path.normcase(api_path.resolve())
        and process_started_at(state["pid"]) == state["started_at"]
    )


def validate_api(state: dict | None, expected_version: str, expected: dict[str, Path]) -> bool:
    if not state_owns_api(state, expected["api"]):
        return False
    try:
        health = request_json(f"{API_URL}/api/health")
        runtime = request_json(f"{API_URL}/api/runtime-info", state["instance_token"])
        return (
            health.get("status") == "ok"
            and runtime.get("version") == expected_version
            and runtime.get("mode") == "portable"
            and runtime.get("instance_token_valid") is True
            and os.path.normcase(Path(runtime["database_path"]).resolve())
            == os.path.normcase((expected["data"] / "whitebox.db").resolve())
            and os.path.normcase(Path(runtime["secrets_path"]).resolve())
            == os.path.normcase(expected["secrets"].resolve())
            and os.path.normcase(Path(runtime["projects_path"]).resolve())
            == os.path.normcase(expected["projects"].resolve())
        )
    except (OSError, KeyError, ValueError, urllib.error.URLError):
        return False


def stop_process(state: dict | None, api_path: Path) -> None:
    if not state_owns_api(state, api_path):
        return
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, state["pid"])
        if handle:
            try:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)


def protect_data(expected: dict[str, Path]) -> None:
    if os.name != "nt":
        return
    try:
        user = os.environ.get("USERNAME")
        if not user:
            return
        subprocess.run(
            ["icacls.exe", str(expected["data"]), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/Q"],
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def start(root: Path, expected: dict[str, Path], no_browser: bool) -> None:
    for directory in (expected["data"], expected["projects"], expected["logs"], expected["state"].parent):
        directory.mkdir(parents=True, exist_ok=True)
    if not expected["api"].is_file() or not expected["version"].is_file():
        raise RuntimeError("分享包文件不完整，请重新解压完整 ZIP。")
    version = json.loads(expected["version"].read_text(encoding="utf-8"))["version"]
    state = read_state(expected["state"])
    if not validate_api(state, version, expected):
        if port_in_use():
            raise RuntimeError(f"本机端口 {API_PORT} 已被其他程序占用，请关闭占用程序后重试。")
        expected["state"].unlink(missing_ok=True)
        token = secrets.token_hex(32)
        environment = {
            **os.environ,
            "WHITEBOX_RUNTIME_MODE": "portable",
            "WHITEBOX_VERSION": version,
            "WHITEBOX_DB": str(expected["data"] / "whitebox.db"),
            "WHITEBOX_SECRETS": str(expected["secrets"]),
            "WHITEBOX_PROJECTS": str(expected["projects"]),
            "WHITEBOX_WEB_DIST": str(expected["web"]),
            "WHITEBOX_INSTANCE_TOKEN": token,
        }
        stdout = (expected["logs"] / "api.log").open("a", encoding="utf-8")
        stderr = (expected["logs"] / "api-error.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            [str(expected["api"])],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        stdout.close()
        stderr.close()
        started_at = process_started_at(process.pid)
        if not started_at:
            process.terminate()
            raise RuntimeError("无法验证 Whitebox API 进程。")
        state = {
            "pid": process.pid,
            "executable_path": str(expected["api"].resolve()),
            "instance_token": token,
            "started_at": started_at,
        }
        expected["state"].write_text(json.dumps(state), encoding="utf-8")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and not validate_api(state, version, expected):
            if process.poll() is not None:
                break
            time.sleep(0.3)
        if not validate_api(state, version, expected):
            stop_process(state, expected["api"])
            expected["state"].unlink(missing_ok=True)
            raise RuntimeError("Whitebox 启动失败，请查看 logs\\api-error.log。")
    protect_data(expected)
    if not no_browser:
        webbrowser.open(API_URL)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()
    root = portable_root()
    expected = paths(root)
    try:
        state = read_state(expected["state"])
        if arguments.stop:
            stop_process(state, expected["api"])
            expected["state"].unlink(missing_ok=True)
            return 0
        start(root, expected, arguments.no_browser)
        return 0
    except Exception as error:
        show_error(str(error), arguments.no_browser)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
