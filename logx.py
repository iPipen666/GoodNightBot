"""logx.py — человекочитаемый логгер + debug-гейт.

Разделяет два потока:
  • farm.log      — только человеческие строки (всегда)
  • farm.debug.log — технич. строки (только при debug=True)
"""

import os
import time
import sys

# --- константы ---
HERE = os.path.dirname(os.path.abspath(__file__))
HUMAN_LOG = os.path.join(HERE, "farm.log")
DEBUG_LOG = os.path.join(HERE, "farm.debug.log")
_STATE = {"debug": False, "log_cb": None}


def setup(debug: bool, log_cb=None) -> None:
    """Инициализация. debug=True -> debug-строки тоже пишутся (в farm.debug.log).
    log_cb -> callback(str) для control.py (получает ТОЛЬКО человеческие строки)."""
    _STATE["debug"] = debug
    _STATE["log_cb"] = log_cb


def _fmt(msg: str) -> str:
    """Формат строки: HH:MM:SS <msg>."""
    return time.strftime("%H:%M:%S") + " " + str(msg)


def log_human(msg) -> None:
    """Человеческая строка. Всегда: stdout + farm.log + (если задан) log_cb панели."""
    line = _fmt(msg)

    # stdout
    try:
        print(line)
    except Exception:
        pass

    # append farm.log
    try:
        with open(HUMAN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    # callback в панель (только человеческие строки)
    cb = _STATE.get("log_cb")
    if cb is not None:
        try:
            cb(str(msg))
        except Exception:
            pass


def log_debug(msg) -> None:
    """Технич. строка (score/координаты/template). Пишется в farm.debug.log ТОЛЬКО
    если setup(debug=True). В панель и farm.log НЕ идёт. No-op если debug=False."""
    if not _STATE.get("debug", False):
        return

    line = _fmt("[dbg] " + str(msg))

    # stdout с префиксом [dbg]
    try:
        print(line, file=sys.stdout)
    except Exception:
        pass

    # append farm.debug.log
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
