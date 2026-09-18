# ホームボタン基板（GPIO）

![ホームボタン基板](../hardware/home-button/render.png)

GPIOヘッダの **35〜40番ピン**（USB端子側の端）に 2x3 ソケットで挿す小基板（12.5×15mm）。
ボタン側は Pi の基板端より外へ張り出す向きに挿す（シルクの `35` `36` がヘッダ側、`HOME` が外側）。

> **状態**: 設計・発注データのみ。実基板は未製作。OS 側の動作は GPIO を模擬して確認済み（後述）。

## 動作

| 操作 | 動作 |
| --- | --- |
| ゲーム中に短押し | ゲームを一時停止(SIGSTOP)して「ゲームを終了しますか？」を表示。A/Enter で決定、B/Esc かホーム短押しでゲームに戻る |
| ゲーム中に長押し(2秒) | 確認なしで終了（SIGTERM、5秒で終わらなければ SIGKILL） |
| ランチャー表示中 | 何もしない |

- OS 側は `/boot/firmware/config.txt` の
  `dtoverlay=gpio-key,gpio=21,active_low=1,gpio_pull=up,keycode=172,label=HOME`
  （`stage-unityconsole/00-base` で追記）が GPIO21 を KEY_HOMEPAGE の入力デバイスにし、
  ランチャーがゲーム実行中だけその evdev を直接読む（X のフォーカスに依存しない）。
  ゲームは独立したプロセスグループで起動し、グループごと停止・終了する。
- ボタンの無い環境でも、USB キーボード等で同じ `KEY_HOMEPAGE` を送れば同じ動作になる
  （ランチャーが読むのは `gpio-keys` ドライバのデバイスのみなので、その場合は `ucon-launcher.py` の `HomeButton` の条件を変更する）。

## 回路

- GPIO21(40番) ─ 1kΩ ─ タクトスイッチ ─ GND(39番)。プルアップは SoC 内蔵（約50kΩ、押下時 約0.07V）。
- 35〜40番の周りには電源ピンが無いので、**逆向き・1列ずれで挿しても信号ピン同士か GND との短絡にしかならない**
  （1kΩ はそのとき出力ピンを GND に落とした場合の電流制限）。
- GPIO21 は I2S の PCM_DOUT と共用。I2S DAC 等の HAT と併用する場合はピン割当の変更が必要。

## 検証（2026-09-16, Pi 4B）

NTsWallpaperEngine 実行中に `pinctrl set 21 pd` / `pu` でボタン押下を模擬し、次を確認した。

- 短押し → 一時停止＋ダイアログ、再度短押し / 「ゲームに戻る」→ 再開、「ゲームを終了する」→ 終了
- 長押し → 約5秒でランチャーへ復帰
- ランチャー表示中の押下 → 無反応

2026-09-18 に 256GB microSD へ焼き直した実機（Type-C 経由 SSH で `ucon-install` したアプリを
ランチャーから起動）でも同じ 4 パターンを再確認した（短押し→一時停止 `T` / 再短押し→再開 / 長押し→終了 /
ランチャー中→無反応）。押下の模擬は上記と同じ `pinctrl set 21 pd`（押す）/ `pu`（離す）。

## 基板データと JLCPCB 発注

`hardware/home-button/` が KiCad 10 プロジェクト（ERC 0件 / DRC 0件・回路図との等価性チェック込み）。
発注用ファイルは `hardware/home-button/jlcpcb/`。

1. `home-button-gerber.zip` をアップロード（2層・1.6mm）。
2. PCB Assembly を有効化。J1（THTソケット）は**裏面**実装なので Standard を選ぶ。
   Economic にする場合は J1 を実装対象から外し、届いた基板に表側からはんだ付けする。
3. `home-button-bom.csv` と `home-button-cpl.csv` をアップロードし、プレビューで
   部品の位置と向き（特に裏面の J1 と SW1）を確認してから注文する。
   J1 の CPL 回転角は JLCPCB 側モデルに合わせて KiCad 出力（-90°）から +90° 補正した 0°
   （補正前はプレビューでソケット本体がパッド列と直交していた）。

| Ref | 部品 | LCSC | 備考 |
| --- | --- | --- | --- |
| SW1 | XKB TS-1187A-B-A-B（5.1mm角・高さ1.5mm・160gf） | C318884 | Basic |
| R1 | 1kΩ 0603 | C21190 | Basic |
| J1 | 2.54mm 2x3 メスソケット 高さ8.5mm（PM254-2-03-Z-8.5） | C2897404 | Extended・THT |

部品のデータシートはリポジトリに含めていない（各部品の LCSC ページから入手できる）。
