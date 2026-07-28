# RasPiOS_UnityConsole

Raspberry Pi をオリジナルゲーム機にするOSイメージ。
Unityで開発したゲーム（Linux x86_64ビルド）を box64 エミュレーションで実行し、
USBメモリ「ゲームカセット」やType-C接続のPCからSDカードへ自動インストールする。

## 対応ハードウェア

- Raspberry Pi 4 / Raspberry Pi 5（arm64・64bitイメージ）
- Pi 5では box64（汎用arm64ビルド、4KBページ前提）のため `kernel=kernel8.img` で4Kページカーネルを使用

## 機能

| 機能 | 実装 |
| --- | --- |
| Unityアプリ実行 | box64 による Linux x86_64 ビルドのエミュレーション実行 |
| Type-C転送 | USBガジェット(CDC-ACM)。PCから `tools/send-app.py` でzipを送ると自動インストール |
| USBカセット | USBメモリ挿入をudevで検知し `/UnityGames/` 配下のzip・フォルダを自動インストール |
| ランチャー | 起動時にフルスクリーンのアプリ一覧を表示（pygame）。アプリ終了後もここに戻る |
| バックアップ | SD容量不足時、ランチャーからアプリをUSBメモリへ退避（USBは再挿入でカセットとして機能） |
| 入力 | USB接続のキーボード/マウス/ゲームパッド、Bluetooth機器（ランチャーにペアリング画面あり） |

## Unityアプリの作り方（要件）

1. Unityで **Linux (x86_64)** をターゲットにビルドする（Unity Personalで可）。
2. Player設定で **Vulkan** を優先Graphics APIにすることを推奨
   （Raspberry PiのOpenGLは3.1相当のため。`-force-vulkan` 起動引数でも可）。
3. ビルド一式をフォルダまたはzipにまとめる:

```
MyGame/                ← この名前がアプリIDになる
  MyGame.x86_64        ← 実行ファイル（必須・1つ）
  MyGame_Data/
  UnityPlayer.so
  game.json            ← 任意: {"name": "表示名", "args": ["-force-vulkan"]}
```

## アプリの入れ方

**方法A: USBメモリ（ゲームカセット）**
USBメモリのルートに `UnityGames/` フォルダを作り、その中にzipまたはビルドフォルダを置いて
本体のType-Aポートに挿すだけ。自動でSDへインストールされ、ランチャーに通知が出る。
（導入済みの同名アプリはスキップされるため、挿しっぱなしでも安全）

**方法B: Type-Cケーブル（PCから転送）**
本体のType-C端子（電源端子）とPCをUSBケーブルで接続すると、PC側にシリアルポート
（Windows: COMx / Linux: /dev/ttyACM0）が現れる。

```
pip install pyserial
python tools/send-app.py COM5 MyGame.zip
```

※ Type-Cからの給電が不足する場合はセルフパワーUSBハブ経由やPD対応ポートを使用。

## 容量不足時の運用

SDカードが一杯でインストールに失敗すると、ランチャーに通知が表示される。
ランチャーでアプリを選び「USBメモリへバックアップ(退避)」を実行すると、
アプリがUSBの `/UnityGames/` へ移動されSD容量が解放される。
退避したアプリはそのUSBを挿し直せば再インストールできる。

## ビルド方法

Cowork（サンドボックス）では実ビルド不可。Linux環境（WSL2可）で:

```bash
# WSL2の場合: リポジトリをLinuxファイルシステムへコピー（NTFS/スペース入りパス不可）
cp -r /mnt/d/Claude\ Coworks\ Projectfile/RaspberryPiOSEditor/RasPiOS_UnityConsole ~/build/
cd ~/build/RasPiOS_UnityConsole

./build-image.sh docker   # Docker Desktop (WSL2バックエンド) 推奨
# または
./build-image.sh native   # Debian/Ubuntu実機 (要 sudo・依存パッケージ)
```

成果物: `pi-gen/deploy/*.img.xz` → Raspberry Pi Imager等でSDカードへ書き込み。

> 注意: box64はビルド時（chroot内）に https://ryanfortner.github.io/box64-debs/
> からインストールされるため、ビルドマシンにインターネット接続が必要。

## 初期アカウント

- ユーザー: `player` / パスワード: `player`（**運用前に必ず変更**）
- ホスト名: `unitycon`、SSH有効（メンテナンス用）

## 構成

```
config                     pi-gen設定 (arm64/trixie, STAGE_LIST)
build-image.sh             ビルドラッパー (pi-gen clone→stage同期→build)
stage-unityconsole/
  00-base/                 パッケージ・boot設定(dwc2/4Kページ)・ディレクトリ・権限
  01-box64/                box64導入 (box64-debsリポジトリ)
  02-gadget/               Type-C USBガジェット(ACM) + シリアル受信サービス
  03-cartridge/            USBカセット自動インストール + バックアップCLI
  04-launcher/             pygameランチャー (tty1キオスクXセッション)
tools/send-app.py          PC側転送ツール (pyserial)
```

### 本体内の主なパス

- アプリ格納: `/var/lib/unityconsole/apps/<アプリ名>/`
- 通知ファイル: `/var/lib/unityconsole/notify.txt`（ランチャーが表示）
- CLI: `ucon-install` / `ucon-backup` / `ucon-usb-install`

## 制約・既知の注意点

- box64エミュレーションのため、重量級3Dゲームは性能不足になり得る（Pi 5推奨）。
- Unity 2021以降のLinuxビルドを想定。IL2CPP/Monoいずれも可。
- OpenGLCoreを要求するビルドは `-force-vulkan` の指定を推奨。
- Pi 4のType-Cはデータ線がガジェット対応。Pi 5も同様だが、給電要件（5V/5A推奨）に注意。
