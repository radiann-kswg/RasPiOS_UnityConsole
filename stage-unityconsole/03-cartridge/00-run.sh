#!/bin/bash -e
# 03-cartridge: USBメモリ(ゲームカセット)自動インストールとバックアップ

install -m 644 files/ucon-lib.sh      "${ROOTFS_DIR}/usr/lib/unityconsole/ucon-lib.sh"
install -m 755 files/ucon-install     "${ROOTFS_DIR}/usr/local/bin/ucon-install"
install -m 755 files/ucon-usb-install "${ROOTFS_DIR}/usr/local/bin/ucon-usb-install"
install -m 755 files/ucon-backup      "${ROOTFS_DIR}/usr/local/bin/ucon-backup"

install -m 644 files/99-unitycon-usb.rules \
    "${ROOTFS_DIR}/etc/udev/rules.d/99-unitycon-usb.rules"
install -m 644 files/unitycon-usb-install@.service \
    "${ROOTFS_DIR}/etc/systemd/system/unitycon-usb-install@.service"

# sudoers: ランチャーからのバックアップ実行を許可（ユーザー名はconfigに追従）
sed "s/^player /${FIRST_USER_NAME} /" files/010_unitycon-sudoers \
    > "${ROOTFS_DIR}/etc/sudoers.d/010_unitycon"
chmod 440 "${ROOTFS_DIR}/etc/sudoers.d/010_unitycon"
