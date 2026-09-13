#!/bin/bash
# UnityConsole 共通ライブラリ（インストール/容量チェック）
# 各CLIから `source /usr/lib/unityconsole/ucon-lib.sh` で読み込む。

APPS_DIR="/var/lib/unityconsole/apps"
NOTIFY_FILE="/var/lib/unityconsole/notify.txt"
MARGIN_KB=204800   # SD空き容量の安全マージン (200MB)

ucon_owner() {
    stat -c %U "${APPS_DIR}" 2>/dev/null || echo root
}

ucon_notify() {
    echo "$*" > "${NOTIFY_FILE}" 2>/dev/null || true
}

# ディレクトリ内のUnity Linuxビルド実行ファイル(*.x86_64)を1つ返す
ucon_find_exe() {
    find "$1" -maxdepth 1 -name '*.x86_64' -type f 2>/dev/null | head -n 1
}

ucon_free_kb() {
    df --output=avail -k "${APPS_DIR}" | tail -n 1 | tr -d ' '
}

ucon_size_kb() {
    du -sk "$1" | cut -f 1
}

# ディレクトリ形式のアプリをSDへインストール
#   $1: ソースディレクトリ  $2: アプリ名
#   戻り値: 0=成功 1=不正 2=容量不足
ucon_install_dir() {
    local src="$1" name="$2"
    local exe need avail dest tmp

    exe="$(ucon_find_exe "${src}")"
    if [ -z "${exe}" ]; then
        echo "実行ファイル(*.x86_64)が見つかりません: ${name}"
        return 1
    fi

    need="$(ucon_size_kb "${src}")"
    avail="$(ucon_free_kb)"
    # du/df が失敗した場合（読み出しエラーのUSB等）に空文字を 0 と誤解して先へ進めない
    if [ -z "${need}" ] || [ -z "${avail}" ]; then
        echo "メディアの読み出しに失敗しました: ${name}"
        return 1
    fi
    if [ "$((need + MARGIN_KB))" -gt "${avail}" ]; then
        echo "空き容量不足: ${name} (必要 $((need / 1024))MB / 空き $((avail / 1024))MB)"
        return 2
    fi

    dest="${APPS_DIR}/${name}"
    tmp="${dest}.tmp.$$"
    rm -rf "${tmp}"
    cp -a "${src}" "${tmp}"
    chmod +x "${tmp}/$(basename "${exe}")"
    chown -R "$(ucon_owner):$(ucon_owner)" "${tmp}"
    rm -rf "${dest}"
    mv "${tmp}" "${dest}"
    sync
    echo "${name}"
    return 0
}

# zip形式のアプリをSDへインストール
#   $1: zipファイルパス
#   戻り値: 0=成功 1=不正 2=容量不足
ucon_install_zip() {
    local zip="$1"
    local tmp name src rc entries

    tmp="$(mktemp -d /var/cache/unityconsole/extract.XXXXXX)"
    if ! unzip -q "${zip}" -d "${tmp}"; then
        rm -rf "${tmp}"
        echo "zipの展開に失敗: $(basename "${zip}")"
        return 1
    fi

    # zip直下が単一ディレクトリならそれをアプリ本体とみなす
    entries=("${tmp}"/*)
    if [ "${#entries[@]}" -eq 1 ] && [ -d "${entries[0]}" ]; then
        src="${entries[0]}"
        name="$(basename "${entries[0]}")"
    else
        src="${tmp}"
        name="$(basename "${zip}" .zip)"
    fi

    ucon_install_dir "${src}" "${name}"
    rc=$?
    rm -rf "${tmp}"
    return "${rc}"
}
