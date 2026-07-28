#!/usr/bin/env python3
"""UnityConsole ランチャー。

SDカードにインストール済みのUnityアプリ一覧をフルスクリーン表示し、
キーボード / ゲームパッドで選択・起動する。アプリ終了後はここに戻る。

操作:
    ↑↓ / 十字キー : 選択移動
    Enter / Aボタン: 決定
    Esc / Bボタン  : 戻る
"""
import json
import os
import shutil
import subprocess
import sys

import pygame

APPS_DIR = "/var/lib/unityconsole/apps"
NOTIFY_FILE = "/var/lib/unityconsole/notify.txt"
RUN_APP = "/usr/local/bin/ucon-run-app"
BACKUP_CMD = ["sudo", "-n", "/usr/local/bin/ucon-backup"]

BG = (16, 18, 28)
FG = (235, 235, 245)
ACCENT = (90, 170, 255)
DIM = (130, 135, 150)
WARN = (255, 190, 80)

AXIS_THRESHOLD = 0.6


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


class Launcher:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)
        self.open_display()
        self.init_joysticks()
        self.clock = pygame.time.Clock()
        self.apps = scan_apps()
        self.cursor = 0
        self.mode = "list"          # list / menu / bt / busy
        self.menu_cursor = 0
        self.bt_devices = []
        self.bt_cursor = 0
        self.message = ""
        self.running = True

    # --- 表示基盤 ---------------------------------------------------------
    def open_display(self):
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("UnityConsole")
        self.w, self.h = self.screen.get_size()
        base = max(18, self.h // 30)
        self.font = pygame.font.SysFont("notosanscjkjp,notosansjp,sans", base)
        self.font_big = pygame.font.SysFont(
            "notosanscjkjp,notosansjp,sans", int(base * 1.6), bold=True)
        self.font_small = pygame.font.SysFont(
            "notosanscjkjp,notosansjp,sans", int(base * 0.75))

    def init_joysticks(self):
        pygame.joystick.init()
        self.joysticks = []
        for i in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(i)
            js.init()
            self.joysticks.append(js)

    def text(self, s, font, color, x, y, center=False):
        surf = font.render(s, True, color)
        rect = surf.get_rect()
        if center:
            rect.midtop = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surf, rect)
        return rect.bottom

    # --- 入力 -------------------------------------------------------------
    def poll_nav(self):
        """イベントを (nav, ok, back) の高レベル操作へ変換。"""
        nav, ok, back = 0, False, False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                self.init_joysticks()
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_UP:
                    nav = -1
                elif ev.key == pygame.K_DOWN:
                    nav = 1
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    ok = True
                elif ev.key == pygame.K_ESCAPE:
                    back = True
            elif ev.type == pygame.JOYHATMOTION:
                if ev.value[1] == 1:
                    nav = -1
                elif ev.value[1] == -1:
                    nav = 1
            elif ev.type == pygame.JOYAXISMOTION and ev.axis in (1, 3):
                if ev.value < -AXIS_THRESHOLD:
                    nav = -1
                elif ev.value > AXIS_THRESHOLD:
                    nav = 1
            elif ev.type == pygame.JOYBUTTONDOWN:
                if ev.button == 0:
                    ok = True
                elif ev.button == 1:
                    back = True
        return nav, ok, back

    # --- アプリ実行 ---------------------------------------------------------
    def run_app(self, app):
        pygame.display.quit()
        try:
            subprocess.run([RUN_APP, app["path"]] + app["args"],
                           check=False)
        finally:
            pygame.display.init()
            self.open_display()
            self.apps = scan_apps()

    def do_backup(self, app):
        self.message = "バックアップ中..."
        self.draw()
        pygame.display.flip()
        r = subprocess.run(BACKUP_CMD + [app["id"]],
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip().splitlines()
        self.message = out[-1] if out else (
            "バックアップ完了" if r.returncode == 0 else "バックアップ失敗")
        self.apps = scan_apps()
        self.cursor = min(self.cursor, max(0, len(self.apps) - 1))

    def do_delete(self, app):
        try:
            shutil.rmtree(app["path"])
            self.message = f"{app['name']} を削除しました"
        except OSError as e:
            self.message = f"削除失敗: {e}"
        self.apps = scan_apps()
        self.cursor = min(self.cursor, max(0, len(self.apps) - 1))

    # --- 描画 -------------------------------------------------------------
    def draw_header(self):
        self.text("UnityConsole", self.font_big, ACCENT, self.w // 2,
                  self.h // 20, center=True)
        self.text(free_space_text(), self.font_small, DIM,
                  self.w - self.w // 20 - 300, self.h // 40)

    def draw_footer(self, hint):
        self.text(hint, self.font_small, DIM, self.w // 2,
                  self.h - self.h // 12, center=True)
        notify = read_notify()
        if notify:
            self.text(notify, self.font_small, WARN, self.w // 2,
                      self.h - self.h // 18, center=True)
        if self.message:
            self.text(self.message, self.font_small, WARN, self.w // 2,
                      self.h - self.h // 25, center=True)

    def draw_list(self):
        items = [a["name"] for a in self.apps] + ["Bluetooth機器のペアリング"]
        y = self.h // 5
        step = int(self.font.get_height() * 1.8)
        visible = max(1, (self.h - y - self.h // 6) // step)
        top = max(0, min(self.cursor - visible // 2, len(items) - visible))
        for i in range(top, min(top + visible, len(items))):
            selected = (i == self.cursor)
            color = FG if not selected else BG
            if selected:
                pygame.draw.rect(
                    self.screen, ACCENT,
                    (self.w // 8, y - step // 6, self.w * 3 // 4, step),
                    border_radius=8)
            label = items[i]
            if i >= len(self.apps):
                label = "⚙ " + label
            self.text(label, self.font, color, self.w // 8 + 24, y)
            y += step
        if not self.apps:
            self.text("インストール済みのUnityアプリがありません",
                      self.font, DIM, self.w // 2, self.h // 2 - 60,
                      center=True)
            self.text("USBメモリ(カセット)を挿すか、Type-CでPCから転送してください",
                      self.font_small, DIM, self.w // 2, self.h // 2,
                      center=True)

    def draw_menu(self):
        app = self.apps[self.cursor]
        self.text(app["name"], self.font_big, FG, self.w // 2,
                  self.h // 4, center=True)
        options = ["起動", "USBメモリへバックアップ(退避)", "削除", "戻る"]
        y = self.h // 2 - 40
        step = int(self.font.get_height() * 1.9)
        for i, opt in enumerate(options):
            selected = (i == self.menu_cursor)
            color = ACCENT if selected else FG
            prefix = "▶ " if selected else "   "
            self.text(prefix + opt, self.font, color, self.w // 3, y)
            y += step

    def draw_bt(self):
        self.text("Bluetooth ペアリング", self.font_big, FG, self.w // 2,
                  self.h // 6, center=True)
        if not self.bt_devices:
            self.text("決定でスキャン開始（約12秒）", self.font, DIM,
                      self.w // 2, self.h // 2, center=True)
            return
        y = self.h // 3
        step = int(self.font.get_height() * 1.8)
        for i, (mac, name) in enumerate(self.bt_devices):
            selected = (i == self.bt_cursor)
            color = ACCENT if selected else FG
            prefix = "▶ " if selected else "   "
            self.text(f"{prefix}{name}  ({mac})", self.font, color,
                      self.w // 6, y)
            y += step

    def draw(self):
        self.screen.fill(BG)
        self.draw_header()
        if self.mode == "list":
            self.draw_list()
            self.draw_footer("↑↓: 選択   Enter/A: 決定")
        elif self.mode == "menu":
            self.draw_menu()
            self.draw_footer("Enter/A: 決定   Esc/B: 戻る")
        elif self.mode == "bt":
            self.draw_bt()
            self.draw_footer("Enter/A: スキャン/ペアリング   Esc/B: 戻る")

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
                pygame.display.flip()
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
                pygame.display.flip()
                try:
                    okpair, detail = bt_pair(mac)
                    self.message = (f"{name} を接続しました" if okpair else
                                    f"ペアリング失敗: {' '.join(detail)}")
                except Exception as e:
                    self.message = f"ペアリング失敗: {e}"

    def loop(self):
        while self.running:
            nav, ok, back = self.poll_nav()
            if self.mode == "list":
                self.update_list(nav, ok, back)
            elif self.mode == "menu":
                self.update_menu(nav, ok, back)
            elif self.mode == "bt":
                self.update_bt(nav, ok, back)
            self.draw()
            pygame.display.flip()
            self.clock.tick(30)


def main():
    launcher = Launcher()
    launcher.loop()
    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
