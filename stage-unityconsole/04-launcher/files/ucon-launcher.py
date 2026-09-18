#!/usr/bin/env python3
"""UnityConsole ランチャー。

SDカードにインストール済みのUnityアプリ一覧をフルスクリーン表示し、
キーボード / ゲームパッドで選択・起動する。アプリ終了後はここに戻る。

画面は 640x360 の論理解像度で描き、整数倍に拡大して表示する（1280x720 なら2倍）。
ピクセルフォントは 患者長ひっく さんの x0y0pxFreeFont（/usr/share/fonts/truetype/00ff/README.md）。

操作:
    ←→↑↓ / 十字キー: 選択移動
    Enter / Aボタン : 決定
    Esc / Bボタン   : 戻る
    ホームボタン    : ゲーム中に短押しで一時停止+終了確認、長押し(2秒)で即終了
"""
import glob
import json
import math
import os
import select
import shutil
import signal
import struct
import subprocess
import sys
import time

import pygame

APPS_DIR = "/var/lib/unityconsole/apps"
NOTIFY_FILE = "/var/lib/unityconsole/notify.txt"
RUN_APP = "/usr/local/bin/ucon-run-app"
BACKUP_CMD = ["sudo", "-n", "/usr/local/bin/ucon-backup"]

FONT_DIR = "/usr/share/fonts/truetype/00ff"
BODY_TTF = FONT_DIR + "/x12y16pxMaruMonica.ttf"     # 本文: 12x16格子・JIS第1/第2水準
HEAD_TTF = FONT_DIR + "/x14y24pxHeadUpDaisy.ttf"    # 見出し: 14x24格子・英数かなのみ
FALLBACK_FONT = "notosanscjkjp,notosansjp,sans"

LOGICAL_W, LOGICAL_H = 640, 360     # 論理解像度（ドット単位）
DIALOG_W, DIALOG_H = 320, 120

# 配色（案B ディスク・ブラウザ）
INK = (5, 6, 10)
GLOW = (30, 44, 98)
MIDNIGHT = (11, 15, 34)
FG = (207, 214, 230)
WHITE = (255, 255, 255)
TITLE = (233, 237, 245)
DIM = (154, 163, 184)
CYAN = (111, 214, 255)
CYAN_HI = (168, 230, 255)
LINE = (35, 42, 68)
ROW_LINE = (30, 36, 56)
TILE_TOP, TILE_BOTTOM, TILE_EDGE, TILE_INK = (34, 42, 68), (15, 18, 32), (52, 61, 92), (138, 147, 170)
SEL_TOP, SEL_BOTTOM = (52, 64, 106), (21, 26, 46)
BT_TOP, BT_BOTTOM = (26, 32, 54), (12, 15, 26)
BAR = (9, 11, 20)
RED = (255, 140, 158)
WARN = (255, 195, 107)
BADGE_B = (26, 32, 54)
POLY_TRI = (143, 180, 255)
POLY_SQ = (178, 140, 255)

# ドット絵（1文字=1ドット）
GEAR = ["....##....", "..#.##.#..", ".########.", "..##..##..", "###....###",
        "###....###", "..##..##..", ".########.", "..#.##.#..", "....##...."]
DISC = ["....######....", "..##LLLLLL##..", ".#LLLLSSLLLL#.", ".#LLLSSSLLLL#.", "#LLLLSLLLLLLL#",
        "#LLLLLL##LLLL#", "#LLLLL#..#LLL#", "#LLLLL#..#LLL#", "#LLLLLL##LLLL#", "#LLLLLLLLLLLL#",
        ".#LLLLLLLLLL#.", ".#LLLLLLLLLL#.", "..##LLLLLL##..", "....######...."]
BADGE = ["..####..", ".#FFFF#.", "#FFFFFF#", "#FFFFFF#", "#FFFFFF#", "#FFFFFF#", ".#FFFF#.", "..####.."]
POINTER = ["....#....", "...###...", "..#####..", ".#######.", "#########"]
ARROW_L = ["....#", "...##", "..###", ".####", "#####", ".####", "..###", "...##", "....#"]

# 背景でゆっくり回る多角形（中心, [(外形), (内側)], 1周の秒数）
DRIFT = [
    ((550, 290), [(0, -129), (129, 101), (-129, 101)], [(0, -84), (90, 73), (-90, 73)], 24, POLY_TRI),
    ((35, 285), [(-74, -74), (74, -74), (74, 74), (-74, 74)], [(-42, -42), (42, -42), (42, 42), (-42, 42)],
     -31, POLY_SQ),
]

DRIFT_TOP = 120    # 回転する多角形はこの行より下にしか来ない（半透明合成の範囲を絞る）

AXIS_THRESHOLD = 0.6    # ここを越えたらスティックを倒したと見なす
AXIS_RELEASE = 0.35     # ここまで戻るまで次の入力を出さない（ヒステリシス）
NAV_AXES = (0, 1, 3, 4)     # 左右スティックの XY。軸 2/5 はトリガーで静止値が -1 なので除く
# ゲームから戻った時に捨てる「操作」イベント。JOYDEVICEADDED/REMOVED は捨てない
# （捨てるとゲーム中に抜き差しされたパッドを取りこぼし、戻った時点で無反応になる）。
CONTROL_EVENTS = (pygame.KEYDOWN, pygame.KEYUP,
                  pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP,
                  pygame.JOYAXISMOTION, pygame.JOYHATMOTION)

# GPIOホームボタン: config.txt の dtoverlay=gpio-key が GPIO21 押下で KEY_HOMEPAGE を発行する
HOME_KEYCODE = 172              # KEY_HOMEPAGE
LONG_PRESS_SEC = 2.0
EV_KEY = 1
INPUT_EVENT = struct.Struct("llHHi")    # struct input_event (64bit)

os.environ.setdefault("SDL_VIDEO_CENTERED", "1")    # 確認ダイアログを画面中央へ

_shutdown = False


def _request_shutdown(signum, frame):
    """SIGTERM/SIGINT で速やかに終了する（systemctl stop/restart が
    90秒待たされて SIGKILL される問題への対策）。ハンドラ内では旗を立てるだけにし、
    実際の後始末（ゲーム終了・pygame.quit）は各ループ側で行う。"""
    global _shutdown
    _shutdown = True


def find_exe(path):
    for entry in sorted(os.listdir(path)):
        if entry.endswith(".x86_64") and os.path.isfile(os.path.join(path, entry)):
            return entry
    return None


def scan_apps():
    apps = []
    if not os.path.isdir(APPS_DIR):
        return apps
    for entry in sorted(os.listdir(APPS_DIR)):
        path = os.path.join(APPS_DIR, entry)
        if not os.path.isdir(path):
            continue
        exe = find_exe(path)
        if not exe:
            continue
        name, args = entry, []
        meta = os.path.join(path, "game.json")
        if os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as f:
                    data = json.load(f)
                name = str(data.get("name", name))
                args = [str(a) for a in data.get("args", [])]
            except (OSError, ValueError):
                pass
        apps.append({"id": entry, "name": name, "path": path, "args": args})
    return apps


def read_notify():
    try:
        with open(NOTIFY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def clear_notify():
    try:
        os.remove(NOTIFY_FILE)
    except OSError:
        pass


def free_space_text():
    try:
        usage = shutil.disk_usage(APPS_DIR)
        return f"SD空き容量: {usage.free / (1024 ** 3):.1f} GB"
    except OSError:
        return ""


def bt_scan():
    """周辺のBluetoothデバイスをスキャンして (mac, name) のリストを返す。"""
    subprocess.run(["bluetoothctl", "power", "on"],
                   capture_output=True, timeout=10)
    subprocess.run(["bluetoothctl", "--timeout", "12", "scan", "on"],
                   capture_output=True, timeout=30)
    result = subprocess.run(["bluetoothctl", "devices"],
                            capture_output=True, text=True, timeout=10)
    devices = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "Device":
            devices.append((parts[1], parts[2]))
    return devices


def bt_pair(mac):
    for cmd in (["pair", mac], ["trust", mac], ["connect", mac]):
        r = subprocess.run(["bluetoothctl"] + cmd,
                           capture_output=True, text=True, timeout=45)
        if r.returncode != 0 and cmd[0] != "connect":
            return False, (r.stdout + r.stderr).strip().splitlines()[-1:]
    return True, []


class HomeButton:
    """ゲーム実行中だけ gpio-keys の evdev を直接読む（Xのフォーカスに依存しない）。"""

    def __init__(self):
        self.fds = []
        self.down_at = None
        for ev in glob.glob("/sys/class/input/event*"):
            driver = os.path.realpath(ev + "/device/device/driver")
            if os.path.basename(driver) != "gpio-keys":
                continue
            try:
                self.fds.append(os.open("/dev/input/" + os.path.basename(ev),
                                        os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass

    def close(self):
        for fd in self.fds:
            os.close(fd)

    def poll(self, timeout):
        """"short"(離した時) / "long"(LONG_PRESS_SEC 押し続けた時点) / None"""
        if self.fds:
            readable = select.select(self.fds, [], [], timeout)[0]
        else:
            time.sleep(timeout)
            readable = []
        result = None
        for fd in readable:
            try:
                data = os.read(fd, INPUT_EVENT.size * 64)
            except OSError:
                continue
            for _, _, typ, code, value in INPUT_EVENT.iter_unpack(data):
                if typ != EV_KEY or code != HOME_KEYCODE:
                    continue
                if value == 1:
                    self.down_at = time.monotonic()
                elif value == 0 and self.down_at is not None:
                    self.down_at = None
                    result = "short"
        if (self.down_at is not None
                and time.monotonic() - self.down_at >= LONG_PRESS_SEC):
            self.down_at = None     # 離した時の "short" を出さない
            result = "long"
        return result


def signal_app(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def stop_app(proc):
    """TERM → 5秒で KILL。一時停止(SIGSTOP)中でも届くよう CONT を続けて送る。"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        signal_app(proc, sig)
        signal_app(proc, signal.SIGCONT)
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass


def sprite(rows, colors):
    surf = pygame.Surface((len(rows[0]), len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                surf.set_at((x, y), colors[ch])
    return surf


def scaled(surf, k):
    if k == 1:
        return surf
    return pygame.transform.scale(surf, (surf.get_width() * k, surf.get_height() * k))


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def vgradient(w, h, top, bottom):
    surf = pygame.Surface((w, h))
    for y in range(h):
        pygame.draw.line(surf, lerp(top, bottom, y / max(1, h - 1)), (0, y), (w - 1, y))
    return surf


def backdrop():
    """radial-gradient(ellipse 90% 70% at 50% 115%, GLOW, MIDNIGHT 55%, INK)。段差は味として残す。"""
    surf = pygame.Surface((LOGICAL_W, LOGICAL_H))
    surf.fill(INK)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps
        color = lerp(GLOW, MIDNIGHT, t / 0.55) if t <= 0.55 else lerp(MIDNIGHT, INK, (t - 0.55) / 0.45)
        rx, ry = 576 * t, 252 * t
        pygame.draw.ellipse(surf, color, pygame.Rect(320 - rx, 414 - ry, rx * 2, ry * 2))
    return surf


def glow_ring(w, h, level):
    """選択枠の外側のにじみ。level 0..1"""
    pad = 8
    surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    for i in range(1, pad + 1):
        a = int((pad + 1 - i) * (10 + 14 * level))
        pygame.draw.rect(surf, CYAN + (min(a, 255),), (pad - i, pad - i, w + i * 2, h + i * 2), 1)
    return surf


def load_font(path, size):
    try:
        return pygame.font.Font(path, size)
    except (OSError, FileNotFoundError):
        return pygame.font.SysFont(FALLBACK_FONT, size)


class Type:
    """ピクセルフォントを原寸でアンチエイリアス無しに描き、整数倍で拡大する。"""

    def __init__(self):
        self.fonts = {"body": load_font(BODY_TTF, 16), "head": load_font(HEAD_TTF, 24)}
        self.cache = {}

    def render(self, s, color, k=1, font="body", spacing=0):
        key = (s, color, k, font, spacing)
        surf = self.cache.get(key)
        if surf is None:
            f = self.fonts[font]
            if spacing:
                glyphs = [f.render(ch, False, color) for ch in s]
                width = sum(g.get_width() for g in glyphs) + spacing * max(0, len(glyphs) - 1)
                surf = pygame.Surface((max(1, width), f.get_height()), pygame.SRCALPHA)
                x = 0
                for g in glyphs:
                    surf.blit(g, (x, 0))
                    x += g.get_width() + spacing
            else:
                surf = f.render(s, False, color).convert_alpha()
            surf = scaled(surf, k)
            if len(self.cache) > 512:
                self.cache.clear()
            self.cache[key] = surf
        return surf

    def width(self, s, k=1):
        return self.fonts["body"].size(s)[0] * k

    def fit(self, s, max_w, k=2):
        """k倍で収まらなければ1倍へ落とし、それでも溢れる分は … で切る。 -> (文字列, 倍率)"""
        if k > 1 and self.width(s, k) <= max_w:
            return s, k
        if self.width(s) <= max_w:
            return s, 1
        while s and self.width(s + "…") > max_w:
            s = s[:-1]
        return s + "…", 1


class Launcher:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)
        self.sprites = {
            "gear": sprite(GEAR, {"#": (106, 115, 144)}),
            "gear_on": sprite(GEAR, {"#": FG}),
            "disc": sprite(DISC, {"#": (11, 61, 92), "L": CYAN, "S": WHITE}),
            "badge_a": sprite(BADGE, {"#": INK, "F": CYAN}),
            "badge_b": sprite(BADGE, {"#": DIM, "F": BADGE_B}),
            "pointer": sprite(POINTER, {"#": CYAN}),
            "arrow_l": sprite(ARROW_L, {"#": DIM}),
        }
        self.sprites["arrow_r"] = pygame.transform.flip(self.sprites["arrow_l"], True, False)
        self.bg = backdrop()
        self.open_display()
        self.joysticks = {}         # instance_id -> Joystick
        self.axis_latch = {}        # (instance_id, axis) -> -1/0/+1
        self.open_joysticks()
        self.clock = pygame.time.Clock()
        self._apps_mtime = None
        self.apps = scan_apps()
        self.cursor = 0
        self.tile_first = 0
        self.mode = "list"          # list / menu / bt
        self.menu_cursor = 0
        self.bt_devices = []
        self.bt_cursor = 0
        self.message = ""
        self.running = True

    # --- 表示基盤 ---------------------------------------------------------
    def open_display(self):
        """全画面で開く。UCON_WINDOW=1280x720 なら窓表示（画面確認用）。"""
        window = os.environ.get("UCON_WINDOW")
        if window:
            self.screen = pygame.display.set_mode(tuple(int(v) for v in window.split("x")))
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("UnityConsole")
        self.use_canvas(LOGICAL_W, LOGICAL_H)
        self.type = Type()
        self.glows = {}
        self.overlay = pygame.Surface((LOGICAL_W, LOGICAL_H - DRIFT_TOP), pygame.SRCALPHA)

    def use_canvas(self, lw, lh):
        sw, sh = self.screen.get_size()
        self.k = max(1, min(sw // lw, sh // lh))
        self.canvas = pygame.Surface((lw, lh)).convert()
        self.screen.fill(INK)
        # 拡大結果を画面へ直接書く（中間サーフェスとblitを省く）
        self.frame = self.screen.subsurface(((sw - lw * self.k) // 2, (sh - lh * self.k) // 2,
                                             lw * self.k, lh * self.k))

    def present(self):
        pygame.transform.scale(self.canvas, self.frame.get_size(), self.frame)
        pygame.display.flip()

    def open_joysticks(self):
        """起動時に接続中のパッドを開く。以後の増減はイベントで追従する。

        ここで pygame.joystick.quit() を呼んではいけない。SDL は joystick
        サブシステムを init するたび、接続中の全デバイスへ JOYDEVICEADDED を
        積み直すため、「ADDED を受けたら quit()+init()」は自分で自分を呼び続ける
        無限ループになる（2026-09-18 実機計測: 4 秒間に 46 回再初期化、30fps→6fps）。
        再初期化のたびに evdev を閉じて開き直すので xpad ドライバの割り込み URB が
        kill/submit を繰り返し、usb_submit_urb -EPERM → EPIPE でパッドが自ら
        USB バスから落ちる（dmesg の xpad_irq_in 失敗と 'unable to receive magic
        message: -32'）。抜き差しのたびに接触不良のように見えていた原因。
        """
        pygame.joystick.init()
        self.close_joysticks()
        for i in range(pygame.joystick.get_count()):
            self.add_joystick(i)

    def close_joysticks(self):
        for js in list(self.joysticks.values()):
            self.quit_joystick(js)
        self.joysticks = {}
        self.axis_latch = {}

    @staticmethod
    def quit_joystick(js):
        """pygame の Joystick は GC では閉じない（dealloc は SDL_JoystickClose を
        呼ばない）。明示的に quit() しないと抜いたパッドの fd が残り続ける。"""
        try:
            js.quit()
        except pygame.error:
            pass

    def add_joystick(self, device_index):
        """JOYDEVICEADDED: 新しく挿さった 1 台だけを開く。"""
        try:
            js = pygame.joystick.Joystick(device_index)
            js.init()
        except pygame.error:
            return
        iid = js.get_instance_id()
        if iid in self.joysticks:
            self.quit_joystick(js)      # 二重 open の分だけ閉じる（SDL は参照数管理）
            return
        self.joysticks[iid] = js

    def remove_joystick(self, instance_id):
        """JOYDEVICEREMOVED: 抜けた 1 台だけを閉じる（他のパッドは触らない）。"""
        js = self.joysticks.pop(instance_id, None)
        if js is not None:
            self.quit_joystick(js)
        self.axis_latch = {k: v for k, v in self.axis_latch.items()
                           if k[0] != instance_id}

    def text(self, s, color, x, y, k=1, align="left", font="body", spacing=0):
        surf = self.type.render(s, color, k, font, spacing)
        rect = surf.get_rect()
        if align == "center":
            rect.midtop = (x, y)
        elif align == "right":
            rect.topright = (x, y)
        else:
            rect.topleft = (x, y)
        self.canvas.blit(surf, rect)
        return rect

    # --- 入力 -------------------------------------------------------------
    def poll_nav(self):
        """イベントを (nav, ok, back) の高レベル操作へ変換。←↑ = -1 / →↓ = +1"""
        nav, ok, back = 0, False, False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.JOYDEVICEADDED:
                self.add_joystick(ev.device_index)
            elif ev.type == pygame.JOYDEVICEREMOVED:
                self.remove_joystick(ev.instance_id)
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_UP, pygame.K_LEFT):
                    nav = -1
                elif ev.key in (pygame.K_DOWN, pygame.K_RIGHT):
                    nav = 1
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    ok = True
                elif ev.key == pygame.K_ESCAPE:
                    back = True
            elif ev.type == pygame.JOYHATMOTION:
                hx, hy = ev.value
                if hy == 1 or hx == -1:
                    nav = -1
                elif hy == -1 or hx == 1:
                    nav = 1
            elif ev.type == pygame.JOYAXISMOTION and ev.axis in NAV_AXES:
                # 倒した瞬間だけ 1 回動かす。閾値ぎりぎりで揺れるスティックだと
                # 素通しでは 1 イベントごとにカーソルが走ってしまう（接触不良に見える）。
                key = (getattr(ev, "instance_id", 0), ev.axis)
                prev = self.axis_latch.get(key, 0)
                if ev.value <= -AXIS_THRESHOLD:
                    now = -1
                elif ev.value >= AXIS_THRESHOLD:
                    now = 1
                elif abs(ev.value) <= AXIS_RELEASE:
                    now = 0
                else:
                    now = prev          # 閾値と復帰閾値の間では状態を変えない
                if now and now != prev:
                    nav = now
                self.axis_latch[key] = now
            elif ev.type == pygame.JOYBUTTONDOWN:
                if ev.button == 0:
                    ok = True
                elif ev.button == 1:
                    back = True
        return nav, ok, back

    # --- アプリ実行 ---------------------------------------------------------
    def run_app(self, app):
        pygame.display.quit()
        home = HomeButton()
        try:
            # 新しいプロセスグループで起動し、ホームボタンでグループごと止める
            proc = subprocess.Popen([RUN_APP, app["path"]] + app["args"],
                                    start_new_session=True)
            while proc.poll() is None:
                if _shutdown:           # systemctl stop/restart: ゲームごと畳んで抜ける
                    stop_app(proc)
                    break
                press = home.poll(0.2)
                if press == "long" or (
                        press == "short" and self.confirm_quit(proc, home)):
                    stop_app(proc)
        finally:
            home.close()
            pygame.display.init()
            self.open_display()
            pygame.event.clear(CONTROL_EVENTS)  # ゲーム中に溜まったパッド入力を捨てる
            self.apps = scan_apps()

    def confirm_quit(self, proc, home):
        """ゲームを一時停止して終了確認ダイアログを出す。True なら終了。"""
        signal_app(proc, signal.SIGSTOP)
        pygame.display.init()
        info = pygame.display.Info()
        self.screen = pygame.display.set_mode(
            (info.current_w // 2, info.current_h // 3), pygame.NOFRAME)
        self.use_canvas(DIALOG_W, DIALOG_H)
        self.type = Type()
        pygame.mouse.set_visible(False)
        pygame.event.clear(CONTROL_EVENTS)
        options = ["ゲームを終了する", "ゲームに戻る"]
        choice = 0
        decided = None
        while decided is None:
            if _shutdown:               # 終了要求が来たらゲームを終了扱いで畳む
                decided = True
                break
            press = home.poll(1 / 30)
            nav, ok, back = self.poll_nav()
            if press == "long":
                decided = True
            elif press == "short" or back:
                decided = False
            elif ok:
                decided = (choice == 0)
            choice = (choice + nav) % len(options)
            self.draw_dialog(options, choice)
            self.present()
        pygame.display.quit()
        if not decided:
            signal_app(proc, signal.SIGCONT)
        return decided

    def do_backup(self, app):
        self.message = "バックアップ中..."
        self.draw()
        self.present()
        r = subprocess.run(BACKUP_CMD + [app["id"]],
                           capture_output=True, text=True)
        if r.stderr:    # 詳細は journal へ（ランチャーの stderr は tty1 に出て見えない）
            subprocess.run(["logger", "-t", "ucon-backup"], input=r.stderr, text=True)
        # 画面には ucon-backup 自身の要約（stdout 最終行）を出す。
        # stderr の最終行（cp 等の内部エラー）を出すと原因が読めない表示になる。
        out = r.stdout.strip().splitlines() or r.stderr.strip().splitlines()
        self.message = out[-1] if out else (
            "バックアップ完了" if r.returncode == 0 else "バックアップ失敗")
        self.apps = scan_apps()
        self.cursor = min(self.cursor, len(self.apps))

    def do_delete(self, app):
        try:
            shutil.rmtree(app["path"])
            self.message = f"{app['name']} を削除しました"
        except OSError as e:
            self.message = f"削除失敗: {e}"
        self.apps = scan_apps()
        self.cursor = min(self.cursor, len(self.apps))

    # --- 描画部品 -----------------------------------------------------------
    def pulse(self, period=1.6):
        return 0.5 - 0.5 * math.cos(time.monotonic() * 2 * math.pi / period)

    def draw_backdrop(self):
        self.canvas.blit(self.bg, (0, 0))
        ov = self.overlay
        ov.fill((0, 0, 0, 0))
        t = time.monotonic()
        for (cx, cy), outer, inner, period, color in DRIFT:
            cy -= DRIFT_TOP
            a = math.radians(t / period * 360)
            ca, sa = math.cos(a), math.sin(a)
            rot = [[(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts] for pts in (outer, inner)]
            pygame.draw.polygon(ov, color + (12,), rot[1])
            pygame.draw.polygon(ov, color + (44,), rot[0], 1)
        self.canvas.blit(ov, (0, DRIFT_TOP))

    def draw_header(self, meter):
        self.text("UNITY CONSOLE", TITLE, 32, 22, font="head", spacing=3)
        try:
            usage = shutil.disk_usage(APPS_DIR)
        except OSError:
            usage = None
        if usage:
            label = f"SD空き容量: {usage.free / (1024 ** 3):.1f} GB"
            if meter:
                self.text(label, DIM, 608, 19, align="right")
                lit = round(16 * usage.free / max(1, usage.total))
                for i in range(16):
                    pygame.draw.rect(self.canvas, CYAN if i < lit else LINE, (418 + i * 12, 40, 10, 6))
            else:
                self.text(label, DIM, 608, 30, align="right")
        pygame.draw.line(self.canvas, LINE, (32, 58), (607, 58))
        pygame.draw.line(self.canvas, CYAN, (32, 58), (99, 58))

    def draw_hints(self, hints):
        """hints: [(キー, ラベル)]。キーが "A"/"B" ならボタン、それ以外は枠付きキー表示。右寄せ。"""
        c = self.canvas
        c.fill(BAR, (0, 322, LOGICAL_W, 38))
        pygame.draw.line(c, LINE, (0, 322), (LOGICAL_W - 1, 322))
        x = 608
        for key, label in reversed(hints):
            x = self.text(label, DIM, x, 333, align="right").left - 6
            if key in ("A", "B"):
                badge = scaled(self.sprites["badge_a" if key == "A" else "badge_b"], 2)
                x -= badge.get_width()
                c.blit(badge, (x, 333))
                self.text(key, INK if key == "A" else TITLE, x + 8, 333, align="center")
            else:
                w = self.type.width(key) + 8
                x -= w
                pygame.draw.rect(c, DIM, (x, 333, w, 16), 1)
                self.text(key, TITLE, x + 4, 333)
            x -= 20

    def gradient(self, size, top, bottom):
        key = (size, top, bottom)
        if key not in self.glows:
            self.glows[key] = vgradient(size, size, top, bottom)
        return self.glows[key]

    def draw_tile(self, x, y, size, label, selected, bt=False):
        c = self.canvas
        if selected:
            level = round(self.pulse() * 7) / 7
            key = (size, level)
            if key not in self.glows:
                self.glows[key] = glow_ring(size + 4, size + 4, level)
            c.blit(self.glows[key], (x - 10, y - 10))
            pygame.draw.rect(c, INK, (x - 2, y - 2, size + 4, size + 4), 2)
            c.blit(self.gradient(size, SEL_TOP, SEL_BOTTOM), (x, y))
            pygame.draw.rect(c, CYAN, (x, y, size, size), 2)
        elif bt:
            c.blit(self.gradient(size, BT_TOP, BT_BOTTOM), (x, y))
            for i in range(0, size, 6):     # 破線の枠
                for rx, ry, rw, rh in ((x + i, y, 3, 1), (x + i, y + size - 1, 3, 1),
                                       (x, y + i, 1, 3), (x + size - 1, y + i, 1, 3)):
                    c.fill(TILE_EDGE, (rx, ry, rw, rh))
        else:
            c.blit(self.gradient(size, TILE_TOP, TILE_BOTTOM), (x, y))
            pygame.draw.rect(c, TILE_EDGE, (x, y, size, size), 1)
        if bt:
            k = size * 3 // 64      # 72→3 / 92→4 / 128→6
            gear = scaled(self.sprites["gear_on" if selected else "gear"], k)
            c.blit(gear, gear.get_rect(center=(x + size // 2, y + size // 2)))
        else:
            k = {72: 2, 92: 3}.get(size, 4)
            surf = self.type.render(label, WHITE if selected else TILE_INK, k)
            c.blit(surf, surf.get_rect(center=(x + size // 2, y + size // 2)))

    def draw_status(self, lines, y, x=None):
        """lines: [(文字列, 色, ディスク絵付き)]。x 未指定なら中央揃え。"""
        for s, color, disc in lines:
            max_w = 576 if x is None else 398
            s, _ = self.type.fit(s, max_w - (20 if disc else 0), k=1)
            w = self.type.width(s) + (20 if disc else 0)
            left = (LOGICAL_W - w) // 2 if x is None else x
            if disc:
                self.canvas.blit(self.sprites["disc"], (left, y + 1))
                left += 20
            self.text(s, color, left, y)
            y += 22

    def monogram(self, name):
        return name[:1].upper() or "?"

    # --- 画面 -------------------------------------------------------------
    def draw_list(self):
        items = [(self.monogram(a["name"]), a["name"]) for a in self.apps]
        items.append(("", "Bluetooth機器のペアリング"))
        n = len(items)
        sel, other, gap = 92, 72, 14
        visible = 1 + (576 - sel) // (other + gap)
        if n <= visible:
            first, count = 0, n
        else:
            self.tile_first = max(min(self.tile_first, self.cursor), self.cursor - visible + 1)
            self.tile_first = max(0, min(self.tile_first, n - visible))
            first, count = self.tile_first, visible
        total = sel + (count - 1) * (other + gap)
        x = (LOGICAL_W - total) // 2
        for i in range(first, first + count):
            is_sel = i == self.cursor
            size = sel if is_sel else other
            y = 95 if is_sel else 101
            self.draw_tile(x, y, size, items[i][0], is_sel, bt=(i == n - 1))
            if is_sel:
                self.canvas.blit(self.sprites["pointer"], (x + size // 2 - 4, 194))
            x += size + gap
        if first > 0:
            self.canvas.blit(self.sprites["arrow_l"], (12, 133))
        if first + count < n:
            self.canvas.blit(self.sprites["arrow_r"], (623, 133))

        name, k = self.type.fit(items[self.cursor][1], 576)
        self.text(name, WHITE, 320, 225 if k == 2 else 233, k=k, align="center")

        lines = []
        notify = read_notify()
        if notify:
            lines.append((notify, CYAN, True))
        if self.message:
            lines.append((self.message, WARN, False))
        if not self.apps:
            lines += [("インストール済みのUnityアプリがありません", FG, False),
                      ("USBメモリ(カセット)を挿すか、Type-CでPCから転送してください", DIM, False)]
        self.draw_status(lines[:2], 266)
        self.draw_hints([("←→", "選択"), ("A", "決定")])

    def draw_panel(self, tile_label, title, rows, cursor, bt=False, hints=()):
        """左に大タイル、右に見出しと選択行。rows: [(文字列, 色)]"""
        self.draw_tile(48, 98, 128, tile_label, True, bt=bt)
        title, k = self.type.fit(title, 382)
        self.text(title, WHITE, 210, 93 if k == 2 else 101, k=k)
        visible = 5
        top = max(0, min(cursor - visible + 1, len(rows) - visible)) if cursor >= visible else 0
        for i, (label, color) in enumerate(rows[top:top + visible]):
            y = 139 + i * 32
            label, _ = self.type.fit(label, 362, k=1)
            if top + i == cursor:
                self.canvas.fill(lerp(CYAN, CYAN_HI, self.pulse()), (210, y, 382, 32))
                self.text(label, INK, 220, y + 8)
            else:
                pygame.draw.line(self.canvas, ROW_LINE, (210, y + 31), (591, y + 31))
                self.text(label, color, 220, y + 8)
        if self.message:
            self.draw_status([(self.message, WARN, False)], 302, x=210)
        self.draw_hints(hints)

    def draw_menu(self):
        app = self.apps[self.cursor]
        rows = [("起動", FG), ("USBメモリへバックアップ(退避)", FG), ("削除", RED), ("戻る", FG)]
        self.draw_panel(self.monogram(app["name"]), app["name"], rows, self.menu_cursor,
                        hints=[("↑↓", "選択"), ("A", "決定"), ("B", "戻る")])

    def draw_bt(self):
        if self.bt_devices:
            rows = [(f"{name}  {mac}", FG) for mac, name in self.bt_devices]
            cursor = self.bt_cursor
        else:
            rows, cursor = [("決定でスキャン開始（約12秒）", FG)], 0
        self.draw_panel("", "Bluetooth ペアリング", rows, cursor, bt=True,
                        hints=[("↑↓", "選択"), ("A", "スキャン/ペアリング"), ("B", "戻る")])

    def draw_dialog(self, options, choice):
        c = self.canvas
        c.fill(MIDNIGHT)
        pygame.draw.rect(c, CYAN, c.get_rect(), 1)
        pygame.draw.line(c, LINE, (12, 29), (DIALOG_W - 13, 29))
        self.text("ゲームを終了しますか？", WHITE, DIALOG_W // 2, 8, align="center")
        for i, opt in enumerate(options):
            y = 38 + i * 26
            if i == choice:
                c.fill(lerp(CYAN, CYAN_HI, self.pulse()), (60, y, 200, 24))
                self.text(opt, INK, DIALOG_W // 2, y + 4, align="center")
            else:
                pygame.draw.line(c, ROW_LINE, (60, y + 23), (259, y + 23))
                self.text(opt, FG, DIALOG_W // 2, y + 4, align="center")
        hint, _ = self.type.fit("A: 決定  B・ホーム: 戻る  ホーム長押し: 終了", DIALOG_W - 16, k=1)
        self.text(hint, DIM, DIALOG_W // 2, 96, align="center")

    def draw(self):
        self.draw_backdrop()
        self.draw_header(meter=(self.mode == "list"))
        if self.mode == "list":
            self.draw_list()
        elif self.mode == "menu":
            self.draw_menu()
        elif self.mode == "bt":
            self.draw_bt()

    # --- 状態遷移 ----------------------------------------------------------
    def update_list(self, nav, ok, back):
        count = len(self.apps) + 1
        if nav:
            self.cursor = (self.cursor + nav) % count
            self.message = ""
        if ok:
            clear_notify()
            if self.cursor < len(self.apps):
                self.mode = "menu"
                self.menu_cursor = 0
            else:
                self.mode = "bt"
                self.bt_devices = []
                self.bt_cursor = 0

    def update_menu(self, nav, ok, back):
        if back:
            self.mode = "list"
            return
        if nav:
            self.menu_cursor = (self.menu_cursor + nav) % 4
        if ok:
            app = self.apps[self.cursor]
            if self.menu_cursor == 0:
                self.mode = "list"
                self.run_app(app)
            elif self.menu_cursor == 1:
                self.do_backup(app)
                self.mode = "list"
            elif self.menu_cursor == 2:
                self.do_delete(app)
                self.mode = "list"
            else:
                self.mode = "list"

    def update_bt(self, nav, ok, back):
        if back:
            self.mode = "list"
            return
        if nav and self.bt_devices:
            self.bt_cursor = (self.bt_cursor + nav) % len(self.bt_devices)
        if ok:
            if not self.bt_devices:
                self.message = "スキャン中..."
                self.draw()
                self.present()
                try:
                    self.bt_devices = bt_scan()
                    self.message = (f"{len(self.bt_devices)}件見つかりました"
                                    if self.bt_devices else
                                    "デバイスが見つかりませんでした")
                except Exception as e:
                    self.message = f"スキャン失敗: {e}"
            else:
                mac, name = self.bt_devices[self.bt_cursor]
                self.message = f"{name} とペアリング中..."
                self.draw()
                self.present()
                try:
                    okpair, detail = bt_pair(mac)
                    self.message = (f"{name} を接続しました" if okpair else
                                    f"ペアリング失敗: {' '.join(detail)}")
                except Exception as e:
                    self.message = f"ペアリング失敗: {e}"

    def refresh_apps(self):
        """apps/ の mtime が変わった時だけ再走査（USBカセット挿入や退避を一覧へ即反映）"""
        try:
            m = os.stat(APPS_DIR).st_mtime
        except OSError:
            m = None
        if m != self._apps_mtime:
            self._apps_mtime = m
            self.apps = scan_apps()
            self.cursor = min(self.cursor, len(self.apps))

    def loop(self):
        while self.running and not _shutdown:
            nav, ok, back = self.poll_nav()
            if self.mode == "list":
                self.refresh_apps()
                self.update_list(nav, ok, back)
            elif self.mode == "menu":
                self.update_menu(nav, ok, back)
            elif self.mode == "bt":
                self.update_bt(nav, ok, back)
            self.draw()
            self.present()
            self.clock.tick(30)


def main():
    launcher = Launcher()
    # pygame.init が入れる SDL 側 SIGTERM ハンドラを、構築後に自前へ上書きする。
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    launcher.loop()
    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
