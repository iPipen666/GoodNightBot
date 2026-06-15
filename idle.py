"""TBH — детект простоя пользователя (для «вежливого» режима бота).

idle_seconds() — сколько секунд назад БЫЛ ЛЮБОЙ ввод (мышь/клава), включая
синтетический (бота). Используется как СТАРТ-гейт: перед циклом бот ждёт, пока
система простаивает >= порога (бот в это время не кликает, значит простой = твой).

cursor_pos() — текущая позиция курсора. Бот запоминает, куда он его поставил;
если курсор УЕХАЛ от этого места (а двигал не бот) — значит ты вернулся -> уступаем.
"""
import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
try:
    _user32.SetProcessDPIAware()
except Exception:
    pass


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    li = _LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not _user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    tick = _kernel32.GetTickCount()
    dt = (tick - li.dwTime) & 0xFFFFFFFF  # обработать переполнение DWORD
    return dt / 1000.0


def cursor_pos():
    p = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
