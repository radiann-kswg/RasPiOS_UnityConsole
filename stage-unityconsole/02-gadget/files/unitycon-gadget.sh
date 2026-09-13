#!/bin/bash
# USBガジェット(複合: CDC-NCM イーサネット + CDC-ACM シリアル)のセットアップ・解除
# Type-C端子でPCと接続すると、PC側には USBネットワークアダプタ(SSH保守リンク)と
# シリアルポート(send-app.py 用)の両方が見える。
# ネットワーク側の機能クラスは /boot/firmware/unitycon.conf の USB_FUNCTION で切替:
#   ncm   (既定) : CDC-NCM。Windows 11 / 10(21H2+) の標準ドライバで動作
#   rndis        : 旧Windows向け。MS OS Descriptorで自動バインド
#   ecm          : CDC-ECM。Linux/macOSホスト向け
# 使い方: unitycon-gadget.sh start|stop
set -eu

CONF=/boot/firmware/unitycon.conf
G=/sys/kernel/config/usb_gadget/unitycon

# --- 設定読み込み（既定値 → confで上書き） ---
USB_FUNCTION="ncm"
PI_IP="10.89.0.1"
PI_PREFIX="24"
if [ -r "${CONF}" ]; then
    # shellcheck disable=SC1090
    . "${CONF}"
fi

serial="$(awk '/^Serial/ {print $3}' /proc/cpuinfo)"
[ -n "${serial}" ] || serial="0000000000000000"
# シリアル由来の決定的なMACアドレス（ローカル管理ビット付き・下位10桁を使用）
mac_base="$(printf '%s' "${serial}" | tail -c 10)"
dev_mac="02:$(echo "${mac_base}" | sed 's/\(..\)\(..\)\(..\)\(..\)\(..\)/\1:\2:\3:\4:\5/')"
host_mac="12:$(echo "${dev_mac}" | cut -c4-)"

start() {
    modprobe libcomposite
    if ! mountpoint -q /sys/kernel/config; then
        mount -t configfs none /sys/kernel/config
    fi

    # ガジェット非対応ポート/機種でも起動失敗にしない
    # sysfs のUDC名は英数字のみのため ls で問題ない
    # shellcheck disable=SC2012
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
    cd "${G}"
    echo 0x1d6b > idVendor      # Linux Foundation
    echo 0x0104 > idProduct     # Multifunction Composite Gadget
    echo 0x0100 > bcdDevice
    echo 0x0200 > bcdUSB
    # 複数機能(IAD)を Windows の usbccgp に正しく分割させるため Misc/Common/IAD を明示
    echo 0xEF > bDeviceClass
    echo 0x02 > bDeviceSubClass
    echo 0x01 > bDeviceProtocol

    mkdir -p strings/0x409
    echo "${serial}"         > strings/0x409/serialnumber
    echo "UnityConsole"      > strings/0x409/manufacturer
    echo "UnityConsole Link" > strings/0x409/product

    mkdir -p configs/c.1/strings/0x409
    echo "usb-ethernet + acm" > configs/c.1/strings/0x409/configuration
    echo 500 > configs/c.1/MaxPower

    # 1) ネットワーク機能 (SSH保守リンク)
    case "${USB_FUNCTION}" in
    rndis)
        mkdir -p functions/rndis.usb0
        echo "${dev_mac}"  > functions/rndis.usb0/dev_addr
        echo "${host_mac}" > functions/rndis.usb0/host_addr
        # MS OS Descriptor: WindowsにRNDISドライバを自動選択させる
        echo 1        > os_desc/use
        echo 0xcd     > os_desc/b_vendor_code
        echo MSFT100  > os_desc/qw_sign
        echo RNDIS    > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
        echo 5162001  > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id
        ln -s functions/rndis.usb0 configs/c.1/
        ln -s configs/c.1 os_desc
        ;;
    ecm)
        mkdir -p functions/ecm.usb0
        echo "${dev_mac}"  > functions/ecm.usb0/dev_addr
        echo "${host_mac}" > functions/ecm.usb0/host_addr
        ln -s functions/ecm.usb0 configs/c.1/
        ;;
    ncm|*)
        mkdir -p functions/ncm.usb0
        echo "${dev_mac}"  > functions/ncm.usb0/dev_addr
        echo "${host_mac}" > functions/ncm.usb0/host_addr
        ln -s functions/ncm.usb0 configs/c.1/
        ;;
    esac

    # 2) シリアル機能 (send-app.py → unitycon-serial-receiver, /dev/ttyGS0)
    mkdir -p functions/acm.GS0
    ln -s functions/acm.GS0 configs/c.1/

    echo "${UDC_NAME}" > UDC

    # usb0 に静的IPを付与（PC側へのDHCP配布は dnsmasq: /etc/dnsmasq.d/usb0.conf）
    ip addr replace "${PI_IP}/${PI_PREFIX}" dev usb0
    ip link set usb0 up
    echo "unitycon-gadget: 有効化しました (UDC=${UDC_NAME}, ${USB_FUNCTION}+acm, ${PI_IP}/${PI_PREFIX})"
}

stop() {
    [ -d "${G}" ] || return 0
    cd "${G}"
    echo "" > UDC 2>/dev/null || true
    rm -f os_desc/c.1 2>/dev/null || true
    find configs/c.1 -maxdepth 1 -type l -delete 2>/dev/null || true
    rmdir configs/c.1/strings/0x409 configs/c.1 2>/dev/null || true
    rmdir functions/* 2>/dev/null || true
    rmdir strings/0x409 2>/dev/null || true
    cd /
    rmdir "${G}" 2>/dev/null || true
}

case "${1:-start}" in
    start) start ;;
    stop)  stop ;;
    *) echo "usage: $0 start|stop" >&2; exit 1 ;;
esac
