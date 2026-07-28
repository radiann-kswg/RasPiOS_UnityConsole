#!/usr/bin/env python3
"""UnityConsole ホスト側転送ツール。

PCとUnityConsole(Raspberry Pi)のType-C端子をUSBケーブルで接続し、
UnityアプリのzipをシリアルCDC-ACM経由で送信・自動インストールする。

必要パッケージ: pyserial  (pip install pyserial)

使い方:
    python send-app.py <シリアルポート> <アプリzip>
    例 (Windows): python send-app.py COM5 MyGame.zip
    例 (Linux)  : python send-app.py /dev/ttyACM0 MyGame.zip

zipの中身: Unityの「Linux x86_64」ビルド一式
    MyGame/
      MyGame.x86_64
      MyGame_Data/
      UnityPlayer.so
      (任意) game.json  {"name": "表示名", "args": ["-force-vulkan"]}
"""
import os
import sys

try:
    import serial
except ImportError:
    print("pyserial が必要です: pip install pyserial", file=sys.stderr)
    sys.exit(1)

CHUNK = 65536


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    port_name, zip_path = sys.argv[1], sys.argv[2]
    if not os.path.isfile(zip_path):
        print(f"ファイルが見つかりません: {zip_path}", file=sys.stderr)
        return 1
    if not zip_path.lower().endswith(".zip"):
        print("zipファイルを指定してください", file=sys.stderr)
        return 1

    size = os.path.getsize(zip_path)
    fname = os.path.basename(zip_path)

    with serial.Serial(port_name, baudrate=115200, timeout=600) as port:
        header = f"UCON1 {size} {fname}\n".encode("utf-8")
        port.write(header)

        sent = 0
        with open(zip_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                port.write(chunk)
                sent += len(chunk)
                pct = sent * 100 // size
                print(f"\r送信中... {pct}% ({sent}/{size} bytes)",
                      end="", flush=True)
        print()

        print("インストール待機中...")
        response = port.readline().decode("utf-8", "replace").strip()

    if response.startswith("OK"):
        print(f"完了: {response[3:]}")
        return 0
    print(f"失敗: {response or '応答なし'}", file=sys.stderr)
    if "NOSPACE" in response:
        print("SDカードの空き容量が不足しています。本体ランチャーの"
              "バックアップ機能でアプリをUSBメモリへ退避してください。",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
