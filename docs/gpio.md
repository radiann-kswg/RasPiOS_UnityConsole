# GPIO 拡張（ゲームから GPIO を使う）

> **状態: 設計段階（2026-09-26 に要件定義）。まだイメージには入っていない。**

Unity ゲームから GPIO を使い、LED・サーボ・I2C センサーなどの**拡張ゲームパーツ**を動かせるようにする。
本体（デーモン・Unity SDK・通信プロトコル）は別リポジトリ
[RasPiLib_UnityGpio](https://github.com/radiann-kswg/RasPiLib_UnityGpio)（**MIT**）にあり、
本リポジトリには `lib/RasPiLib_UnityGpio/` にサブモジュールとして入っている。

- 要件と確定事項: [lib/RasPiLib_UnityGpio/docs/requirements.md](https://github.com/radiann-kswg/RasPiLib_UnityGpio/blob/main/docs/requirements.md)
- 構成・推奨ピン配置・SDK の API 草案: [lib/RasPiLib_UnityGpio/docs/architecture.md](https://github.com/radiann-kswg/RasPiLib_UnityGpio/blob/main/docs/architecture.md)
- 通信プロトコル: [lib/RasPiLib_UnityGpio/docs/protocol.md](https://github.com/radiann-kswg/RasPiLib_UnityGpio/blob/main/docs/protocol.md)

## 役割分担（ライセンス境界）

| 置き場所 | 中身 | ライセンス |
| --- | --- | --- |
| `lib/RasPiLib_UnityGpio/` | デーモン `unitygpiod`、Unity SDK、プロトコル、汎用の導入スクリプト | MIT |
| 本リポジトリ | 下記の「UnityConsole 側の設定」と、イメージへの組み込み | CC BY-SA 4.0 |

ゲームに組み込まれるのは MIT の SDK だけなので、ゲーム側に CC BY-SA の条件は及ばない。

## UnityConsole 側の設定（v1）

| 項目 | 値 | 理由 |
| --- | --- | --- |
| 予約ピン | `21` | ホームボタン（`dtoverlay=gpio-key,gpio=21,...`）。ゲームからは確保できない |
| I2C（GPIO2/3） | 既定で**無効**（仮） | 使わないゲームではデジタル入出力に回せるように。公式 OS と同じく既定オフ |
| PWM（GPIO12/13） | 既定で**無効**（仮） | 同上 |
| 遠隔モードの TCP | 既定で**無効** | 開発時だけ有効にする（下記） |
| ゲームの実行ユーザー | `player`（`gpio` グループ） | pi-gen の初期ユーザーは `gpio` グループに入る想定（実装時に実機の `id player` で確認） |

I2C・PWM を使うゲームを遊ぶときは、SSH で次を実行して再起動する（または PC で SD の `config.txt` を編集する）。

```bash
sudo unitygpio-config i2c on
sudo unitygpio-config pwm on
sudo reboot
```

## ゲーム機としての振る舞い

| 場面 | 動作 |
| --- | --- |
| ゲーム終了（ランチャーへ戻る・ホームボタン長押し・異常終了） | デーモンが切断を検知し、出力を入力に戻す・PWM 停止・LED 消灯 |
| ホームボタン短押しで一時停止（SIGSTOP） | v1 は出力を**そのまま保持**。v2 以降、ランチャーがデーモンへ一時停止を通知し、ピンごとの `safeOnPause` に従わせる |
| 同時に動くゲーム | 1 本だけ（`ucon-run-app` の制限）。デーモンも 1 接続だけ受け付ける |
| `game.json` | v1 では GPIO の宣言は持たない。使えないピンやバスは実行時にエラーで分かる |

## ピンについて

- 物理 35〜40 番ピンは**ホームボタン基板が塞ぐ**。35〜38 番（GPIO19・16・26・20）を使いたい場合は、
  ホームボタン基板を改版せず、HAT や 2x20 のブレークアウト用パーツ（垂直水平両用のピンヘッダ等）で引き出す。
- 拡張パーツを作るときは、RasPiLib_UnityGpio の推奨ピン配置表に従う。

## Editor からの開発

- Unity Editor では既定で**模擬モード**（実機不要）。
- 実機で試すときは**遠隔モード**: 実機の `/etc/unitygpio.conf` で TCP を有効にし（待受アドレスとトークンを書く）、
  Editor のプロジェクト設定に実機のアドレスとトークンを入れる。
  接続先は有線 LAN（`192.168.10.x` など）でも Type-C の USB リンク（`10.89.0.1`）でもよい。
- 実機でゲームが動いている間は接続できない（1 接続だけのため）。先にランチャーへ戻ってから接続する。

## 組み込み（実装時の予定）

1. 新しいサブステージ（例: `05-gpio/`）で、`on_chroot` 内から
   `lib/RasPiLib_UnityGpio/daemon/install.sh --no-start` を実行し、予約ピン `21` を書いた `/etc/unitygpio.conf` を置く。
   cloud-init 除去のサブステージは `06-` に繰り下げ、**必ず最後**のままにする。
2. `build-image.sh` が `lib/RasPiLib_UnityGpio/` を pi-gen の作業場所へ同期する。
3. 実機試験は Pi 4B と Pi 5 の両方で行う: デジタル入出力（LED とタクトスイッチ）、エッジイベント、
   PWM（サーボ）、I2C（`i2cdetect` で見えるデバイス 1 つ）、ゲームを SIGKILL したときの後始末、GPIO21 の拒否。
