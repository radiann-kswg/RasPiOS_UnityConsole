#!/bin/bash -e
# 00-base: ブート設定・ディレクトリ・ユーザー権限の基本構成

# --- config.txt: USBガジェットモード & Pi5の4Kページカーネル ---
cat >> "${ROOTFS_DIR}/boot/firmware/config.txt" << 'EOF'

# --- UnityConsole ---
# Type-C端子をUSBペリフェラル(ガジェット)として使用 (Pi 4 / Pi 5)
dtoverlay=dwc2,dr_mode=peripheral

[pi5]
# box64(汎用arm64ビルド)は4KBページ前提のため、Pi 5でも4Kページカーネルを使用
kernel=kernel8.img

[all]
EOF

# --- cmdline.txt: dwc2モジュールをブート時ロード ---
sed -i 's/rootwait/rootwait modules-load=dwc2/' "${ROOTFS_DIR}/boot/firmware/cmdline.txt"

# --- アプリ格納ディレクトリ ---
install -d -m 755 "${ROOTFS_DIR}/var/lib/unityconsole"
install -d -m 755 "${ROOTFS_DIR}/var/lib/unityconsole/apps"
install -d -m 755 "${ROOTFS_DIR}/var/cache/unityconsole"
install -d -m 755 "${ROOTFS_DIR}/var/cache/unityconsole/incoming"
install -d -m 755 "${ROOTFS_DIR}/usr/lib/unityconsole"

# --- X: 一般ユーザーからのstartxを許可（tty1でのキオスク起動用） ---
install -d -m 755 "${ROOTFS_DIR}/etc/X11"
cat > "${ROOTFS_DIR}/etc/X11/Xwrapper.config" << 'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

on_chroot << CHEOF
# 入力・映像・音声デバイスへのアクセス権
usermod -aG input,video,render,audio,plugdev "${FIRST_USER_NAME}"
if getent group bluetooth > /dev/null; then
    usermod -aG bluetooth "${FIRST_USER_NAME}"
fi

# アプリ領域の所有者
chown -R "${FIRST_USER_NAME}:${FIRST_USER_NAME}" /var/lib/unityconsole /var/cache/unityconsole

# ランチャーがtty1を占有するためgettyを無効化
systemctl disable getty@tty1.service

# ユーザーサービス(pipewire等)を常時起動可能に（chroot内ではloginctl不可のため直接作成）
install -d -m 755 /var/lib/systemd/linger
touch "/var/lib/systemd/linger/${FIRST_USER_NAME}"

# Bluetooth有効化
systemctl enable bluetooth.service
CHEOF
