"""launcher.py — EXE-лаунчер GoodNightBot «для чайника»: запустил → всё ставится само →
работает. Ноль действий пользователя. Компилируется PyInstaller'ом в .exe с иконкой.

Поток:
  1) venv уже есть -> сразу запускаем панель.
  2) нет Python в системе -> СКАЧИВАЕМ и ставим Python (per-user, тихо, без админа) со сплэшем.
  3) запускаем bootstrap.py найденным Python -> он сам делает venv + зависимости + Tesseract+рус
     -> открывает панель (со своим pixel-art загрузчиком).
"""
import os
import sys
import time
import threading
import subprocess
import urllib.request

APP = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
BOOT = os.path.join(APP, "bootstrap.py")
CONTROL = os.path.join(APP, "control.py")
VENV_PYW = os.path.join(APP, ".venv", "Scripts", "pythonw.exe")
ICON = os.path.join(APP, "icon.ico")
FLAGS = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW

PYTHON_URL = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
NIGHT, PANEL, MOON, INK, SUB = "#171229", "#221a3d", "#f6e3a1", "#ece8fb", "#9a8fce"


def _child_env():
    """Чистое окружение для дочерних процессов: убрать загрязнение PyInstaller
    (_MEIPASS в PATH + TCL/TK_LIBRARY), иначе дочерний venv-python ломается на импортах."""
    env = dict(os.environ)
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        env["PATH"] = os.pathsep.join(
            p for p in env.get("PATH", "").split(os.pathsep) if mei.lower() not in p.lower())
    for k in ("TCL_LIBRARY", "TK_LIBRARY", "TKPATH", "_PYI_APPLICATION_HOME_DIR",
              "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
        env.pop(k, None)
    return env


def _py_ok(exe):
    """Кандидат — РЕАЛЬНЫЙ python 3.10–3.12 (запускаем и проверяем версию). Отсекает WindowsApps-заглушку
    (она не выполняет -c, открывает Store), старые версии И слишком новые: rapidocr_onnxruntime требует
    <3.13, на 3.13/3.14 колесо OCR не ставится. Нет подходящего → ставим bundled 3.12.7."""
    if not exe or not os.path.exists(exe):
        return False
    try:
        r = subprocess.run([exe, "-c", "import sys;print(sys.version_info[0],sys.version_info[1])"],
                           capture_output=True, text=True, creationflags=FLAGS, timeout=20)
        p = r.stdout.split()
        return r.returncode == 0 and len(p) >= 2 and int(p[0]) == 3 and 10 <= int(p[1]) <= 12
    except Exception:
        return False


def find_python():
    """Системный python ≥3.10 (НЕ этот exe). Источники: py-лаунчер (все версии) → PATH → РЕЕСТР
    (python.org) → Store → типовые пути. Каждый кандидат ВАЛИДИРУЕТСЯ запуском. None если нет."""
    import shutil
    cands = []
    for arg in ("-3.13", "-3.12", "-3.11", "-3.10", "-3"):
        try:
            out = subprocess.run(["py", arg, "-c", "import sys;print(sys.executable)"],
                                 capture_output=True, text=True, creationflags=FLAGS, timeout=15)
            if out.returncode == 0 and out.stdout.strip():
                cands.append(out.stdout.strip())
        except Exception:
            pass
    for name in ("python", "python3", "python.exe"):
        p = shutil.which(name)
        if p:
            cands.append(p)
    try:                                            # реестр: python.org-инсталляции (per-user и all-users)
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flag in (0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
                try:
                    base = winreg.OpenKey(root, r"SOFTWARE\Python\PythonCore", 0, winreg.KEY_READ | flag)
                except OSError:
                    continue
                for i in range(winreg.QueryInfoKey(base)[0]):
                    try:
                        ver = winreg.EnumKey(base, i)
                        ip = winreg.QueryValue(winreg.OpenKey(base, ver + r"\InstallPath"), None)
                        cands.append(os.path.join(ip, "python.exe"))
                    except OSError:
                        pass
    except Exception:
        pass
    la = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in (la, pf, pf86, r"C:\\"):
        for v in ("Python313", "Python312", "Python311", "Python310"):
            for sub in ((), ("Programs", "Python", v), ("Python", v)):
                cands.append(os.path.join(base, *sub, "python.exe"))
    if la:                                          # Microsoft Store python (реальная установка)
        import glob
        cands += glob.glob(os.path.join(la, "Microsoft", "WindowsApps",
                                        "PythonSoftwareFoundation.Python.3.*", "python.exe"))
    seen = set()
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            if _py_ok(c):
                return c
    return None


def install_python(status):
    """Скачать и тихо поставить Python (per-user, без админа). status(text) — апдейт сплэша."""
    try:
        status("скачиваю Python… (~25 МБ)")
        dst = os.path.join(os.environ.get("TEMP", APP), "python-setup.exe")
        req = urllib.request.Request(PYTHON_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as r, open(dst, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        status("устанавливаю Python… (~1-2 мин)")
        subprocess.run([dst, "/quiet", "InstallAllUsers=0", "PrependPath=1",
                        "Include_pip=1", "Include_launcher=1", "Include_test=0"],
                       creationflags=FLAGS, timeout=600, env=_child_env())
    except Exception:
        pass
    return find_python()


class Splash:
    """Минимальный сплэш на время установки Python (bootstrap покажет свой загрузчик потом)."""
    def __init__(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=NIGHT)
        w, h = 420, 150
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.attributes("-topmost", True)
        try:
            self.root.iconbitmap(ICON)
        except Exception:
            pass
        tk.Label(self.root, text="GoodNightBot", bg=NIGHT, fg=MOON,
                 font=("Consolas", 20, "bold")).pack(pady=(26, 2))
        tk.Label(self.root, text="первичная установка — подождите",
                 bg=NIGHT, fg=SUB, font=("Consolas", 9)).pack()
        self.msg = tk.Label(self.root, text="готовлю…", bg=NIGHT, fg=INK, font=("Consolas", 9))
        self.msg.pack(pady=(12, 0))

    def set(self, text):
        try:
            self.msg.config(text=text)
        except Exception:
            pass

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


_DEPS_CHECK = "import cv2,mss,pyautogui,numpy,pygetwindow,keyboard,pydirectinput,pytesseract"


def _venv_ready():
    """venv есть И зависимости реально импортируются. Битый/недокачанный venv (остаток от
    прошлой неудачной установки) НЕ считается готовым — иначе control стартует без cv2/numpy и
    молча падает (pythonw, без окна). Тогда уходим в bootstrap — он догонит зависимости."""
    if not (os.path.exists(VENV_PYW) and os.path.exists(CONTROL)):
        return False
    try:
        return subprocess.run([VENV_PYW, "-c", _DEPS_CHECK], creationflags=FLAGS,
                              timeout=40, env=_child_env()).returncode == 0
    except Exception:
        return False


def main():
    # уже установлено И рабочее -> сразу панель
    if _venv_ready():
        subprocess.Popen([VENV_PYW, CONTROL], cwd=APP, creationflags=FLAGS, env=_child_env())
        return

    py = find_python()
    if py:
        _launch(py)
        return

    # Python нет -> ставим сами. Со сплэшем, если tkinter доступен; иначе молча.
    try:
        sp = Splash()
    except Exception:
        sp = None
    if sp is None:
        _launch(install_python(lambda *_: None) or find_python())
        return
    result = {"py": None}

    def work():
        result["py"] = install_python(sp.set)
        sp.set("запускаю…")
        time.sleep(0.4)
        sp.root.after(0, sp.root.quit)

    threading.Thread(target=work, daemon=True).start()
    sp.root.mainloop()
    sp.close()
    _launch(result["py"] or find_python())


def _launch(py):
    if py and os.path.exists(BOOT):
        subprocess.Popen([py, BOOT], cwd=APP, creationflags=FLAGS, env=_child_env())
    elif py and os.path.exists(CONTROL):
        subprocess.Popen([py, CONTROL], cwd=APP, creationflags=FLAGS, env=_child_env())
    else:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "Не удалось поставить Python автоматически.\n"
                   "Поставь Python 3.10+ с python.org и запусти снова.", "GoodNightBot", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
