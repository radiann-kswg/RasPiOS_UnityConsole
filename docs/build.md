# イメージのビルド

[pi-gen](https://github.com/RPi-Distro/pi-gen)（arm64 ブランチ）に独自ステージ `stage-unityconsole/` を足して
64bit の Raspberry Pi OS Lite（Debian trixie）ベースのイメージを作る。pi-gen 本体は改変しない。

| 項目 | 内容 |
| --- | --- |
| ビルド環境 | Debian / Ubuntu（x86_64 可）、または Windows の WSL2（Ubuntu 24.04）+ Docker |
| ネットワーク | 必須（pi-gen・Debian / Raspberry Pi のアーカイブ・box64-debs から取得する） |
| 所要時間 | 約1時間（WSL2 + Docker で実測 56 分） |
| 成果物 | `pi-gen/deploy/image_<日付>-RasPiOS-UnityConsole.img.xz`（約 760MB、展開後 約 3.5GB） |

## 手順

```bash
# 1. Linux のファイルシステム上へ clone する（パスに空白を含めない。WSL2 なら /mnt/c 等は不可）
git clone https://github.com/radiann-kswg/RasPiOS_UnityConsole.git ~/workspaces/RasPiOS_UnityConsole
cd ~/workspaces/RasPiOS_UnityConsole

# 2. ホスト側の準備（Docker モードでも qemu の binfmt 登録が必要）
sudo apt install -y qemu-user-static binfmt-support

# 3. ビルド
./build-image.sh docker   # Docker を使う（既定）
# または
./build-image.sh native   # Debian/Ubuntu 上で直接（pi-gen の依存パッケージと sudo が必要）
```

`build-image.sh` は pi-gen の clone、`stage3`〜`stage5` のスキップ、`config` のコピー、
独自ステージの同期と実行ビットの付与までを行う。書き込みは Raspberry Pi Imager の
「カスタムイメージを使う」などで行う。

長時間かかるので、対話シェルから回すときはバックグラウンドで起動してログを追うとよい。

```bash
nohup setsid ./build-image.sh docker > build.log 2>&1 &
tail -f build.log
```

## 注意点

- **Docker モードでもホストに qemu の binfmt 登録が必要**。`pi-gen/build-docker.sh` はコンテナ起動前に確認し、無ければ即終了する。
- **WSL2 では binfmt が自動登録されない**（systemd-binfmt が WSL を除外する）。
  動的リンク版の `qemu-aarch64` が選ばれるとコンテナ内で失敗するため、静的版を F フラグ付きで登録してからビルドする:

  ```bash
  sudo sh -c '
  [ -f /proc/sys/fs/binfmt_misc/register ] || mount binfmt_misc -t binfmt_misc /proc/sys/fs/binfmt_misc
  [ ! -f /proc/sys/fs/binfmt_misc/qemu-aarch64-rpi ] || echo -1 > /proc/sys/fs/binfmt_misc/qemu-aarch64-rpi
  printf "%s" ":qemu-aarch64-rpi:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/bin/qemu-aarch64-static:F" > /proc/sys/fs/binfmt_misc/register'
  ```

- 再実行の前に `docker rm -f pigen_work`（残っていると "already exists" で止まる）。
- 本リポジトリは arm64 ブランチ（Debian 公式アーカイブ）を使うため、armhf 側で必要な
  Raspbian 署名鍵の SHA-1 回避（`SEQUOIA_CRYPTO_POLICY`）は不要。
- box64 はビルド中（chroot 内）に https://ryanfortner.github.io/box64-debs/ から導入する。
- Windows で checkout した作業ツリーを WSL へコピーしてビルドする場合は、改行コード（CRLF）を
  **テキストファイルだけ** LF に直す。同梱フォント（`.ttf`）は `\r` のバイトを含むので、
  全ファイルに `sed` をかけると壊れる:

  ```bash
  find . -path ./pi-gen -prune -o -type f -print0 | xargs -0 grep -lIZ $'\r' | xargs -0 -r sed -i 's/\r$//'
  ```

## 構成

| パス | 内容 |
| --- | --- |
| `config` | pi-gen 設定（arm64 / trixie、ホスト名 `unitycon`、初期ユーザー `player`、`ENABLE_CLOUD_INIT=0`、`STAGE_LIST`） |
| `stage-unityconsole/00-base/` | パッケージ、`config.txt`（dwc2・ホームボタン・Pi 5 の 4K ページカーネル）、ディレクトリ・権限 |
| `stage-unityconsole/01-box64/` | box64 の導入 |
| `stage-unityconsole/02-gadget/` | Type-C USB 複合ガジェット（NCM + ACM）、dnsmasq、シリアル受信サービス |
| `stage-unityconsole/03-cartridge/` | USB カセット自動インストール、退避（バックアップ）CLI、sudoers |
| `stage-unityconsole/04-launcher/` | ランチャー（tty1 のキオスク X セッション）、同梱フォント |
| `stage-unityconsole/05-purge-cloud-init/` | cloud-init の除去（下記） |

## cloud-init について

pi-gen の `stage2/04-cloud-init/00-packages` は `cloud-init` と `rpi-cloud-init-mods` を
**無条件**に導入する。`config` の `ENABLE_CLOUD_INIT=0` が抑止するのは
`boot/firmware/{meta-data,user-data,network-config}` の配置だけで、パッケージ本体と systemd ユニットは残る。

本リポジトリでは `stage-unityconsole/05-purge-cloud-init/` を最後のサブステージとして置き、
明示的に `apt-get purge` している。先行サブステージで導入したパッケージが
`autoremove` の巻き添えにならないよう、**このサブステージは必ず最後**に置くこと。
このため Raspberry Pi Imager の OS カスタマイズ（ユーザー名・Wi-Fi 等）は想定していない（反映されない場合がある）。
