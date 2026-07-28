#!/usr/bin/env python3
"""UnityConsole シリアル受信サービス。

Type-C(USBガジェット/CDC-ACM)経由でPCからUnityアプリのzipを受信し、
SDカードへ自動インストールする。

プロトコル (ホスト側は tools/send-app.py を使用):
    ホスト → Pi : b"UCON1 <size> <filename>\n" + <sizeバイトのzipデータ>
    Pi → ホスト: b"OK <message>\n" または b"ERR <message>\n"
"""
import os
import subprocess
import sys
import time
import tty

DEV = "/dev/ttyGS0"
INCOMING_DIR = "/var/cache/unityconsole/incoming"
NOTIFY_FILE = "/var/lib/unityconsole/notify.txt"
INSTALL_CMD = "/usr/local/bin/ucon-install"
MAX_SIZE = 8 * 1024 ** 3  # 8 GiB
CHUNK = 65536


def log(msg: str) -> None:
    print(msg, flush=True)


def notify(msg: str) -> None:
    """ランチャーの通知欄に表示するメッセージを書き込む。"""
    try:
        with open(NOTIFY_FILE, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def open_port() -> int:
    """ttyGS0が現れるまで待ってrawモードで開く。"""
    while not os.path.exists(DEV):
        time.sleep(2)
    fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(fd)
    return fd


def read_line(fd: int, limit: int = 512) -> bytes:
    """改行までを読み取る。切断時は OSError。"""
    buf = bytearray()
    while len(buf) < limit:
        b = os.read(fd, 1)
        if b == b"":
            raise OSError("port closed")
        if b == b"\n":
            break
        buf += b
    return bytes(buf)


def send(fd: int, text: str) -> None:
    try:
        os.write(fd, text.encode("utf-8", "replace") + b"\n")
    except OSError:
        pass


def recv_to_file(fd: int, size: int, path: str) -> None:
    remaining = size
    with open(path, "wb") as f:
        while remaining > 0:
            data = os.read(fd, min(CHUNK, remaining))
            if data == b"":
                raise OSError("transfer interrupted")
            f.write(data)
            remaining -= len(data)


def sanitize_name(raw: str) -> str:
    name = os.path.basename(raw.strip())
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    if not name.lower().endswith(".zip"):
        name += ".zip"
    return name or "app.zip"


def handle_transfer(fd: int, header: bytes) -> None:
    parts = header.decode("utf-8", "replace").split(maxsplit=2)
    if len(parts) != 3 or parts[0] != "UCON1":
        send(fd, "ERR bad header")
        return
    try:
        size = int(parts[1])
    except ValueError:
        send(fd, "ERR bad size")
        return
    if size <= 0 or size > MAX_SIZE:
        send(fd, "ERR size out of range")
        return

    fname = sanitize_name(parts[2])
    os.makedirs(INCOMING_DIR, exist_ok=True)
    path = os.path.join(INCOMING_DIR, fname)

    log(f"receiving {fname} ({size} bytes)")
    notify(f"受信中: {fname}")
    try:
        recv_to_file(fd, size, path)
    except OSError as e:
        notify(f"受信失敗: {fname} ({e})")
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    log("received, installing...")
    result = subprocess.run(
        [INSTALL_CMD, path],
        capture_output=True, text=True, timeout=3600,
    )
    message = (result.stdout or result.stderr or "").strip().splitlines()
    message = message[-1] if message else ""
    try:
        os.remove(path)
    except OSError:
        pass

    if result.returncode == 0:
        send(fd, f"OK {message}")
        notify(f"インストール完了: {message}")
    elif result.returncode == 2:
        send(fd, f"ERR NOSPACE {message}")
        notify("SDカードの空き容量が不足しています。ランチャーのバックアップ機能で"
               "アプリをUSBメモリへ退避してください。")
    else:
        send(fd, f"ERR {message}")
        notify(f"インストール失敗: {message}")


def main() -> None:
    log("unitycon-serial-receiver: start")
    while True:
        try:
            fd = open_port()
            log(f"opened {DEV}")
            while True:
                header = read_line(fd)
                if header.strip() == b"":
                    continue
                handle_transfer(fd, header)
        except OSError as e:
            log(f"port error: {e}; reopening")
            try:
                os.close(fd)
            except Exception:
                pass
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
