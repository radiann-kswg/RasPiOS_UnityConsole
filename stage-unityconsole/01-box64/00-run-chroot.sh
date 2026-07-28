#!/bin/bash -e
# 01-box64: box64 (x86_64 → ARM64 変換レイヤー) の導入
# Unity の Linux x86_64 ビルドを実行するためのエミュレーション基盤。
# box64-debs リポジトリ (https://ryanfortner.github.io/box64-debs/) を使用。
# 汎用arm64ビルド 'box64' は Pi 4 / Pi 5 共通で動作する（4Kページ前提）。

install -d -m 755 /usr/share/keyrings
curl -fsSL https://ryanfortner.github.io/box64-debs/KEY.gpg \
    | gpg --dearmor -o /usr/share/keyrings/box64-debs-archive-keyring.gpg

cat > /etc/apt/sources.list.d/box64.list << 'EOF'
deb [signed-by=/usr/share/keyrings/box64-debs-archive-keyring.gpg] https://ryanfortner.github.io/box64-debs/debian ./
EOF

apt-get update
apt-get install -y box64

# binfmt登録が無い環境でも動くよう、実行は常に `box64 <exe>` 明示呼び出しとする
box64 --version || true
