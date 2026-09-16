#!/bin/bash -e
# 04-launcher: フルスクリーンランチャー（キオスクXセッション）

install -m 755 files/ucon-launcher.py "${ROOTFS_DIR}/usr/lib/unityconsole/ucon-launcher.py"
install -m 755 files/ucon-xsession    "${ROOTFS_DIR}/usr/lib/unityconsole/ucon-xsession"
install -m 755 files/ucon-run-app     "${ROOTFS_DIR}/usr/local/bin/ucon-run-app"

# ランチャー用ピクセルフォント（患者長ひっく x0y0pxFreeFont。規約は fonts/README.md）
install -d -m 755 "${ROOTFS_DIR}/usr/share/fonts/truetype/00ff"
install -m 644 files/fonts/x12y16pxMaruMonica.ttf files/fonts/x14y24pxHeadUpDaisy.ttf files/fonts/README.md \
    "${ROOTFS_DIR}/usr/share/fonts/truetype/00ff/"

# サービスのUser=はconfigのFIRST_USER_NAMEに追従させる
sed "s/^User=player$/User=${FIRST_USER_NAME}/" files/unitycon-launcher.service \
    > "${ROOTFS_DIR}/etc/systemd/system/unitycon-launcher.service"
chmod 644 "${ROOTFS_DIR}/etc/systemd/system/unitycon-launcher.service"

on_chroot << EOF
systemctl enable unitycon-launcher.service
systemctl set-default multi-user.target
EOF
