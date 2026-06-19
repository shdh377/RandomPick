# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox
import random
import os
import winreg
import json
import threading
import base64
import urllib.request
import tempfile
import wave
import winsound
import ctypes
import ctypes.wintypes


APP_NAME = "RandomPicker"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

dwmapi = ctypes.windll.dwmapi


def get_exe_path():
    if getattr(__import__('sys'), 'frozen', False):
        return __import__('sys').executable
    return os.path.abspath(__file__)


def get_data_dir():
    return os.path.dirname(get_exe_path())


def get_names_file():
    return os.path.join(get_data_dir(), "names.json")


def get_config_file():
    return os.path.join(get_data_dir(), "config.json")


def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{get_exe_path()}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def set_rounded_corners(hwnd):
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        attr = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(attr),
            ctypes.sizeof(attr)
        )
    except Exception:
        pass


BG_COLOR = "#f5f5f5"
BTN_BG = "#e0e0e0"
ACCENT = "#1976d2"
TEXT_COLOR = "#333333"

TTS_URL = "https://api.xiaomimimo.com/v1/chat/completions"


class FloatingPicker:
    def __init__(self, root):
        self.root = root
        self.root.title("随机点名")
        self.root.geometry("120x52+100+100")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.85)
        self.root.configure(bg=BG_COLOR)

        self.names = []
        self.tts_enabled = False
        self.tts_api_key = ""
        self.tts_voice = "mimo_default"

        self._drag_data = {"x": 0, "y": 0}
        self._build_ui()
        self._load_config()
        self._load_saved_names()

        self.root.update_idletasks()
        set_rounded_corners(self.root.winfo_id())

    def _build_ui(self):
        container = tk.Frame(self.root, bg=BG_COLOR)
        container.pack(fill=tk.BOTH, expand=True)

        self.drag_btn = tk.Label(container, text="☰", font=("Segoe UI", 20),
                                 bg=BTN_BG, fg=TEXT_COLOR, width=3, cursor="fleur")
        self.drag_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(2, 0), pady=2)
        self.drag_btn.bind("<ButtonPress-1>", self._start_drag)
        self.drag_btn.bind("<B1-Motion>", self._on_drag)
        self.drag_btn.bind("<ButtonRelease-1>", self._end_drag)
        self.drag_btn.bind("<Double-Button-1>", self._show_menu)

        self.pick_btn = tk.Label(container, text="🎲", font=("Segoe UI", 22),
                                 bg=ACCENT, fg="white", width=3, cursor="hand2")
        self.pick_btn.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2), pady=2)
        self.pick_btn.bind("<Button-1>", self._on_pick)
        self.pick_btn.bind("<Enter>", lambda e: self.pick_btn.config(bg="#1565c0"))
        self.pick_btn.bind("<Leave>", lambda e: self.pick_btn.config(bg=ACCENT))

        self.root.bind("<Button-3>", self._show_menu)

    def _start_drag(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, event):
        pass

    def _show_menu(self, event=None):
        menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei", 10))
        menu.add_command(label="导入名单(TXT)", command=self.import_file)
        menu.add_command(label="手动输入", command=self.manual_input)
        menu.add_separator()
        menu.add_command(label="语音设置", command=self._show_tts_settings)
        tts_var = tk.BooleanVar(value=self.tts_enabled)
        menu.add_checkbutton(label="语音播报", variable=tts_var,
                             command=lambda: self._toggle_tts(tts_var.get()))
        menu.add_separator()
        autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        menu.add_checkbutton(label="开机自启", variable=autostart_var,
                             command=lambda: set_autostart(autostart_var.get()))
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_tts_settings(self):
        win = tk.Toplevel(self.root)
        win.title("语音设置")
        win.geometry("360x240")
        win.configure(bg=BG_COLOR)
        win.attributes("-topmost", True)

        tk.Label(win, text="API Key:", font=("Microsoft YaHei", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=(10, 2))
        api_entry = tk.Entry(win, font=("Microsoft YaHei", 10), width=40, show="*")
        api_entry.pack(pady=2)
        api_entry.insert(0, self.tts_api_key)

        tk.Label(win, text="音色 (voice):", font=("Microsoft YaHei", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=(10, 2))
        voice_entry = tk.Entry(win, font=("Microsoft YaHei", 10), width=40)
        voice_entry.pack(pady=2)
        voice_entry.insert(0, self.tts_voice)

        def save():
            self.tts_api_key = api_entry.get().strip()
            self.tts_voice = voice_entry.get().strip() or "mimo_default"
            self._save_config()
            win.destroy()

        def test():
            key = api_entry.get().strip()
            voice = voice_entry.get().strip() or "mimo_default"
            if not key:
                messagebox.showwarning("提示", "请先填写 API Key", parent=win)
                return
            threading.Thread(target=self._test_tts, args=(key, voice), daemon=True).start()

        btn_frame = tk.Frame(win, bg=BG_COLOR)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="保存", font=("Microsoft YaHei", 10), command=save,
                  bg=ACCENT, fg="white", relief="flat").pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="测试", font=("Microsoft YaHei", 10), command=test,
                  bg="#4caf50", fg="white", relief="flat").pack(side=tk.LEFT, padx=10)

    def _toggle_tts(self, enabled):
        self.tts_enabled = enabled
        self._save_config()

    def _load_config(self):
        try:
            path = get_config_file()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.tts_enabled = cfg.get("tts_enabled", False)
                self.tts_api_key = cfg.get("tts_api_key", "")
                self.tts_voice = cfg.get("tts_voice", "mimo_default")
        except Exception:
            pass

    def _save_config(self):
        try:
            cfg = {
                "tts_enabled": self.tts_enabled,
                "tts_api_key": self.tts_api_key,
                "tts_voice": self.tts_voice
            }
            with open(get_config_file(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
        except Exception:
            pass

    def _test_tts(self, api_key, voice):
        try:
            payload = json.dumps({
                "model": "mimo-v2.5-tts",
                "messages": [
                    {"role": "assistant", "content": "测试语音"}
                ],
                "audio": {
                    "format": "wav",
                    "voice": voice
                }
            }).encode("utf-8")
            req = urllib.request.Request(TTS_URL, data=payload, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            audio_b64 = data["choices"][0]["message"]["audio"]["data"]
            audio_bytes = base64.b64decode(audio_b64)
            self._play_audio(audio_bytes)
        except Exception as e:
            print(f"TTS Test Error: {e}")

    def _on_pick(self, event=None):
        if not self.names:
            self._show_ceremony("请先导入名单", is_error=True)
            return
        chosen = random.choice(self.names)
        self._show_ceremony(chosen)
        if self.tts_enabled and self.tts_api_key:
            threading.Thread(target=self._speak, args=(chosen,), daemon=True).start()

    def _speak(self, text):
        try:
            payload = json.dumps({
                "model": "mimo-v2.5-tts",
                "messages": [
                    {"role": "assistant", "content": text}
                ],
                "audio": {
                    "format": "wav",
                    "voice": self.tts_voice
                }
            }).encode("utf-8")
            req = urllib.request.Request(TTS_URL, data=payload, headers={
                "Authorization": f"Bearer {self.tts_api_key}",
                "Content-Type": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            audio_b64 = data["choices"][0]["message"]["audio"]["data"]
            audio_bytes = base64.b64decode(audio_b64)
            self._play_audio(audio_bytes)
        except Exception as e:
            print(f"TTS Error: {e}")

    def _play_audio(self, audio_bytes):
        tmp = os.path.join(tempfile.gettempdir(), "rp_tts.wav")
        try:
            with open(tmp, "wb") as f:
                f.write(audio_bytes)
            winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            try:
                with wave.open(tmp, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(audio_bytes)
                winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                print(f"Audio Error: {e}")

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
        if not lines:
            messagebox.showwarning("提示", "文件为空或格式不正确")
            return
        self._load_names(lines)

    def manual_input(self):
        win = tk.Toplevel(self.root)
        win.title("输入名单")
        win.geometry("280x300")
        win.configure(bg=BG_COLOR)
        win.attributes("-topmost", True)

        tk.Label(win, text="每行输入一个姓名:", font=("Microsoft YaHei", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=4)

        text = tk.Text(win, font=("Microsoft YaHei", 11), width=18, height=12, bg="white", fg=TEXT_COLOR)
        text.pack(padx=8, pady=4)

        if self.names:
            text.insert("1.0", "\n".join(self.names))

        def confirm():
            content = text.get("1.0", tk.END)
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            if not lines:
                messagebox.showwarning("提示", "请输入至少一个姓名", parent=win)
                return
            self._load_names(lines)
            win.destroy()

        tk.Button(win, text="确定", font=("Microsoft YaHei", 10), command=confirm,
                  bg=ACCENT, fg="white", relief="flat", activebackground="#1565c0").pack(pady=6)

    def _load_names(self, lines):
        seen = set()
        unique = []
        for n in lines:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        self.names = unique
        self._save_names()

    def _save_names(self):
        try:
            with open(get_names_file(), "w", encoding="utf-8") as f:
                json.dump(self.names, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_saved_names(self):
        try:
            path = get_names_file()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self.names = json.load(f)
        except Exception:
            self.names = []

    def _show_ceremony(self, name, is_error=False):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.6)
        popup.configure(bg="#fff0f0" if is_error else "#f5f5f5")

        lbl = tk.Label(popup, text=name,
                       font=("Microsoft YaHei", 24 if is_error else 72, "bold"),
                       bg="#fff0f0" if is_error else "#f5f5f5",
                       fg="#e53935" if is_error else "#1976d2",
                       padx=60, pady=40)
        lbl.pack()

        popup.update_idletasks()
        w = lbl.winfo_reqwidth()
        h = lbl.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        popup.geometry(f"+{(screen_w - w) // 2}+{(screen_h - h) // 2}")

        set_rounded_corners(popup.winfo_id())
        popup.after(3000, popup.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    app = FloatingPicker(root)
    root.mainloop()
