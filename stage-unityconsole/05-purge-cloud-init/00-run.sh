#!/bin/bash -e
# cloud-init の除去
#
# pi-gen の stage2/04-cloud-init/00-packages は cloud-init / rpi-cloud-init-mods を
# 「無条件」に導入する。config の ENABLE_CLOUD_INIT=0 が抑止するのは
# stage2/04-cloud-init/01-run.sh による boot/firmware/{meta-data,user-data,network-config}
# の配置だけで、パッケージ本体と systemd ユニットはイメージに残る。
# ゲーム機用途では不要かつ起動時間を延ばすため、本ステージで明示的に除去する。
#
# ※ 本ステージはカスタムステージの最後に置くこと。
#    先行サブステージで導入したパッケージが autoremove の巻き添えにならないようにするため。

on_chroot << 'EOF'
set -e
export DEBIAN_FRONTEND=noninteractive

# 自動削除がネットワーク管理まで巻き込まないよう、明示的に手動導入扱いへ変更する
apt-mark manual network-manager >/dev/null 2>&1 || true

PURGE_LIST=""
for pkg in cloud-init rpi-cloud-init-mods; do
	if dpkg -l "${pkg}" 2>/dev/null | grep -q '^ii'; then
		PURGE_LIST="${PURGE_LIST} ${pkg}"
	fi
done

if [ -n "${PURGE_LIST}" ]; then
	# shellcheck disable=SC2086
	apt-get -y purge ${PURGE_LIST}
	apt-get -y autoremove --purge
	apt-get clean
fi

if dpkg -l cloud-init 2>/dev/null | grep -q '^ii'; then
	# 除去できなかった場合の保険として無効化フラグを置く
	install -d -m 755 /etc/cloud
	touch /etc/cloud/cloud-init.disabled
else
	rm -rf /etc/cloud /var/lib/cloud
	rm -f /var/log/cloud-init.log /var/log/cloud-init-output.log
fi
EOF
