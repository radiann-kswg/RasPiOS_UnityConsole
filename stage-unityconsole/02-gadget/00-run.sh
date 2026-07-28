#!/bin/bash -e
# 02-gadget: Type-C USBガジェット(シリアル)とアプリ受信サービス

install -m 755 files/unitycon-gadget.sh          "${ROOTFS_DIR}/usr/lib/unityconsole/unitycon-gadget.sh"
install -m 755 files/unitycon-serial-receiver.py "${ROOTFS_DIR}/usr/lib/unityconsole/unitycon-serial-receiver.py"
install -m 644 files/unitycon-gadget.service          "${ROOTFS_DIR}/etc/systemd/system/unitycon-gadget.service"
install -m 644 files/unitycon-serial-receiver.service "${ROOTFS_DIR}/etc/systemd/system/unitycon-serial-receiver.service"

on_chroot << EOF
systemctl enable unitycon-gadget.service
systemctl enable unitycon-serial-receiver.service
EOF
