#!/bin/bash
# USBガジェット(シリアル/CDC-ACM)のセットアップ・解除
# Type-C端子でPCと接続すると、PC側にはシリアルポートとして見える。
# 使い方: unitycon-gadget.sh start|stop
set -e

G=/sys/kernel/config/usb_gadget/unitycon

start() {
    modprobe libcomposite
    if ! mountpoint -q /sys/kernel/config; then
        mount -t configfs none /sys/kernel/config
    fi

    # ガジェット非対応ポート/機種でも起動失敗にしない
    UDC_NAME="$(ls /sys/class/udc 2>/dev/null | head -n 1)"
    if [ -z "${UDC_NAME}" ]; then
        echo "unitycon-gadget: UDCが見つかりません（ガジェットモード非対応環境）。スキップします。"
        exit 0
    fi

    if [ -d "${G}" ]; then
        echo "unitycon-gadget: 既に構成済み"
        exit 0
    fi

    mkdir -p "${G}"
    echo 0x1d6b > "${G}/idVendor"      # Linux Foundation
    echo 0x0104 > "${G}/idProduct"     # Multifunction Composite Gadget
    echo 0x0100 > "${G}/bcdDevice"
    echo 0x0200 > "${G}/bcdUSB"

    mkdir -p "${G}/strings/0x409"
    echo "UNITYCON0001"        > "${G}/strings/0x409/serialnumber"
    echo "UnityConsole"        > "${G}/strings/0x409/manufacturer"
    echo "UnityConsole Serial" > "${G}/strings/0x409/product"

    mkdir -p "${G}/configs/c.1/strings/0x409"
    echo "ACM Serial" > "${G}/configs/c.1/strings/0x409/configuration"
    echo 250 > "${G}/configs/c.1/MaxPower"

    mkdir -p "${G}/functions/acm.GS0"
    ln -sf "${G}/functions/acm.GS0" "${G}/configs/c.1/"

    echo "${UDC_NAME}" > "${G}/UDC"
    echo "unitycon-gadget: 有効化しました (UDC=${UDC_NAME})"
}

stop() {
    if [ -d "${G}" ]; then
        echo "" > "${G}/UDC" 2>/dev/null || true
        rm -f "${G}/configs/c.1/acm.GS0"
        rmdir "${G}/configs/c.1/strings/0x409" "${G}/configs/c.1" \
              "${G}/functions/acm.GS0" "${G}/strings/0x409" "${G}" 2>/dev/null || true
    fi
}

case "${1:-start}" in
    start) start ;;
    stop)  stop ;;
    *) echo "usage: $0 start|stop" >&2; exit 1 ;;
esac
