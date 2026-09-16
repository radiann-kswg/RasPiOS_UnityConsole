# 保守・運用メモ

## Type-C の USB リンク

本体の Type-C 端子（電源端子）と PC を USB ケーブルでつなぐと、Pi は給電を受けつつ
USB 複合ガジェット（CDC-NCM + CDC-ACM）として PC に見える。

| 機能 | PC 側の見え方 | 用途 |
| --- | --- | --- |
| NCM（ネットワーク） | Windows: 「UsbNcm Host Device」 / Linux: `usb0` 等 | SSH 保守。Pi は `10.89.0.1`、PC は DHCP で `10.89.0.10〜20` を取得 |
| ACM（シリアル） | Windows: `COMx` / Linux: `/dev/ttyACM0` | `tools/send-app.py` によるアプリ転送 |

- Windows 11 と Windows 10（21H2 以降）は標準ドライバで両方認識する。
- ネットワーク側の方式はブートパーティションの `unitycon.conf`（`/boot/firmware/unitycon.conf`）の
  `USB_FUNCTION=ncm|rndis|ecm` で切り替えられる（SD カードを PC で開いて編集できる）。シリアル側は常に有効。
- Pi 側 IP を変える場合は `unitycon.conf` の `PI_IP` と `/etc/dnsmasq.d/usb0.conf` を揃える。
- 起動（初回はパーティション拡張の再起動込み）から SSH に届くまで約1分半。
- Type-C 1本で給電すると、PC のポートによっては電力が足りない。
  セルフパワー USB ハブや PD 対応ポートを使う（Pi 5 は 5V/5A 推奨）。

```bash
ssh player@10.89.0.1        # 初期パスワード player。最初に passwd で変更する
```

`sudo` はパスワードを求める（ランチャーからの退避コマンドだけは sudoers でパスワード不要）。

## ファイルだけ更新する（再ビルド不要）

`stage-unityconsole/*/files/` の変更は、各サブステージの `00-run.sh` と同じ `install` を実機で行えば反映できる。
ランチャーの例:

```bash
scp stage-unityconsole/04-launcher/files/ucon-launcher.py player@10.89.0.1:/tmp/
ssh -t player@10.89.0.1 'sudo install -m 755 /tmp/ucon-launcher.py /usr/lib/unityconsole/ucon-launcher.py \
  && sudo systemctl restart unitycon-launcher'
```

- Windows で編集したファイルは改行コードを LF にしてから送る。
- `unitycon-gadget.service` は再起動しない（USB リンク自体が切れる。反映は Pi の再起動で）。
- **退避やカセット導入の最中にランチャーを再起動しない**。退避コマンドはランチャーのサービスの一部として動いているため一緒に止まる
  （SD 側のアプリは最後まで消さない作りなので失われはしない）。
- `config.txt`・パッケージ・box64 を変えた場合はイメージの再ビルドが必要。

## USB カセット（自動インストール）

- USB メモリ（FAT32 / exFAT / NTFS）を挿すと、udev が `unitycon-usb-install@<デバイス>.service` を起動し、
  読み込み専用でマウントして `/UnityGames/`（無ければルート直下）の zip とフォルダを SD へ導入する。
- `*.x86_64` を含むフォルダだけが対象。`.` で始まる隠しフォルダは対象外。導入済みの同名アプリはスキップする。
- FAT32 では実行ビットが失われるが、導入時に付け直す。
- 1件ずつ容量を確認し（200MB の余裕を残す）、足りない場合は通知で退避を案内する。
- 読み出し不良のメディアで固まらないよう、ユニットには 900 秒の上限がある。
- ログ: `journalctl -u 'unitycon-usb-install@*'`

### Pi 4 の USB 3.0（青）ポートについて

Type-C 1本で給電している構成で、USB メモリを青いポートに挿すと SuperSpeed で認識されるものの、
データの読み出しだけが 30 秒でタイムアウトし、デバイスのリセットを繰り返して導入が進まないことがあった
（`dmesg` に `reset SuperSpeed USB device`、`vcgencmd get_throttled` は `0x0` のまま）。
**黒い USB 2.0 ポートに挿す**と解消する（274MB / 395 ファイルを約76秒で導入）。

## SD 容量不足と USB への退避

ランチャーでアプリを選び「USBメモリへバックアップ(退避)」を実行すると、
アプリが USB メモリの `/UnityGames/` へ移動し、SD の容量が空く。そのUSBを挿し直せば再インストールされる。

- FAT32 / exFAT の USB メモリでよい。所有者・パーミッションは保存しない（実行ビットは再インストール時に付け直す）。
- USB 上ではいったん `UnityGames/.<アプリ名>.tmp.<PID>` へコピーし、サイズを検証してから差し替える。
  失敗しても USB 上の既存コピーと SD 側のアプリは残る。
- 必要容量は USB 側のクラスタサイズで見積もる（FAT32 は 32KB、exFAT は 128KB が普通で、SD 上の実サイズより大きくなる）。
- カセット導入中（USB を読み込み専用で使用中）は退避できない。導入の通知が出てから実行する。
- 画面には `ucon-backup` の要約が出る。詳細は `journalctl -t ucon-backup`。

## 本体内の主なパス

| パス | 内容 |
| --- | --- |
| `/var/lib/unityconsole/apps/<アプリ名>/` | インストール済みアプリ |
| `/var/lib/unityconsole/notify.txt` | ランチャーに表示する通知 |
| `/usr/lib/unityconsole/ucon-launcher.py` | ランチャー |
| `/usr/local/bin/ucon-run-app` | アプリ起動（box64 と Mesa の設定） |
| `/usr/local/bin/ucon-install` / `ucon-usb-install` / `ucon-backup` | 導入・カセット導入・退避の CLI |
| `/usr/share/fonts/truetype/00ff/` | ランチャー用ピクセルフォント |
| `~player/.config/unity3d/<会社名>/<製品名>/Player.log` | Unity アプリのログ |

## ランチャーの画面確認

`UCON_WINDOW=1280x720` を付けて起動すると、全画面ではなく窓で開く（PC の Linux 上でも動く。
その場合はフォントを `/usr/share/fonts/truetype/00ff/` に置くか、無ければ Noto Sans CJK で表示される）。

```bash
UCON_WINDOW=1280x720 python3 stage-unityconsole/04-launcher/files/ucon-launcher.py
```

## 既知の注意点

- Raspberry Pi の GPU（V3D）は OpenGL 3.1 相当を報告する。`ucon-run-app` が Mesa の設定で 3.3 相当に引き上げるため、
  Unity の OpenGLCore ビルドがそのまま動く（NTsWallpaperEngine で確認）。Vulkan は未検証。
- box64 によるエミュレーションのため CPU 負荷が高い（上記アプリで 1 コア飽和・常駐メモリ約 0.8〜0.9GB）。重い 3D ゲームは厳しい。
- Pi 5 は設定（4K ページカーネル `kernel8.img`）を入れてあるが、実機では未検証。
- Unity 2021 以降の Linux (x86_64) ビルドを想定。IL2CPP / Mono いずれも可。
