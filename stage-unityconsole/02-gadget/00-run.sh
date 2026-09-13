#!/bin/bash -e
# 02-gadget: Type-C USBガジェット(NCMネットワーク + ACMシリアル)とアプリ受信サービス
#   ネットワーク側: SSH保守リンク (Pi=10.89.0.1、PCへは dnsmasq が 10.89.0.10-20 を配布)
#   シリアル側    : send-app.py からのアプリ受信 (/dev/ttyGS0)

install -m 755 files/unitycon-gadget.sh          "${ROOTFS_DIR}/usr/lib/unityconsole/unitycon-gadget.sh"
install -m 755 files/unitycon-serial-receiver.py "${ROOTFS_DIR}/usr/lib/unityconsole/unitycon-serial-receiver.py"
install -m 644 files/unitycon-gadget.service          "${ROOTFS_DIR}/etc/systemd/system/unitycon-gadget.service"
install -m 644 files/unitycon-serial-receiver.service "${ROOTFS_DIR}/etc/systemd/system/unitycon-serial-receiver.service"

# dnsmasq: usb0 に対する DHCP サーバ設定
install -m 644 files/usb0.conf "${ROOTFS_DIR}/etc/dnsmasq.d/usb0.conf"

# NetworkManager から usb0 を除外（unitycon-gadget.sh が静的に管理する）
install -m 644 files/90-unitycon.conf "${ROOTFS_DIR}/etc/NetworkManager/conf.d/90-unitycon.conf"

# 利用者向け設定ファイル（ブートパーティション: Windowsから編集可能）
install -m 644 files/unitycon.conf "${ROOTFS_DIR}/boot/firmware/unitycon.conf"

on_chroot << EOF
systemctl enable unitycon-gadget.service
systemctl enable unitycon-serial-receiver.service
systemctl enable dnsmasq.service
EOF
