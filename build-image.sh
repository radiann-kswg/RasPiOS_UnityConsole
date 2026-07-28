#!/bin/bash
# RasPiOS_UnityConsole イメージビルドラッパー
# 使い方: ./build-image.sh [docker|native]
#   docker (既定): pi-gen の build-docker.sh を使用
#   native       : sudo ./build.sh を使用（Debian/Ubuntu、依存パッケージ要）
set -euo pipefail

MODE="${1:-docker}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PI_GEN_DIR="${REPO_DIR}/pi-gen"
PI_GEN_URL="https://github.com/RPi-Distro/pi-gen.git"
PI_GEN_BRANCH="arm64"   # 64bit/arm64 (Pi 4 / Pi 5 向け、box64にARM64必須)

case "${REPO_DIR}" in
  *" "*)
    echo "エラー: パスにスペースが含まれています (${REPO_DIR})" >&2
    echo "スペースを含まない場所（WSL2なら ~/ 以下）へコピーして実行してください。" >&2
    exit 1
    ;;
esac

# 1. pi-gen 取得
if [ ! -d "${PI_GEN_DIR}" ]; then
  git clone --depth 1 --branch "${PI_GEN_BRANCH}" "${PI_GEN_URL}" "${PI_GEN_DIR}"
fi

# 2. カスタムステージを pi-gen 内へ同期（Dockerビルドでもコンテナに入るように）
rsync -a --delete "${REPO_DIR}/stage-unityconsole/" "${PI_GEN_DIR}/stage-unityconsole/"

# 3. 実行ビット付与（Windows経由のcheckoutで失われるため明示的に）
find "${PI_GEN_DIR}/stage-unityconsole" -name "*.sh" -exec chmod +x {} +

# 4. 不要ステージをスキップ
touch "${PI_GEN_DIR}/stage3/SKIP" "${PI_GEN_DIR}/stage4/SKIP" "${PI_GEN_DIR}/stage5/SKIP"
touch "${PI_GEN_DIR}/stage2/SKIP_IMAGES" \
      "${PI_GEN_DIR}/stage4/SKIP_IMAGES" "${PI_GEN_DIR}/stage5/SKIP_IMAGES"

# 5. 設定コピー
cp "${REPO_DIR}/config" "${PI_GEN_DIR}/config"

# 6. ビルド実行
cd "${PI_GEN_DIR}"
case "${MODE}" in
  docker) ./build-docker.sh ;;
  native) sudo ./build.sh ;;
  *) echo "不明なモード: ${MODE} (docker|native)" >&2; exit 1 ;;
esac

echo
echo "ビルド完了。成果物: ${PI_GEN_DIR}/deploy/"
ls -lh "${PI_GEN_DIR}/deploy/" || true
