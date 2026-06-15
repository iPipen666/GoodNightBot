"""TBH — ЖИВОЙ пробник рангов инвентаря (только чтение, без кликов).

Калибрует сетку инвентаря (F8 по центру левой-верхней и правой-нижней ячейки),
потом каждую секунду печатает РАНГ каждого слота по цвету РАМКИ (периметр ячейки).

Ранги по цвету рамки (OpenCV hue 0-179):
  красный(<10|>170)=Красный ранг, оранж/золото(10-34)=Легендарный,
  зелёный(35-85)=Необычный, синий(86-128)=Редкий, фиолет(129-160)=Эпик,
  белый/серый/пусто=Обычный.

Угловой красный 'X' (класс не носит) отличаем от красного РАНГА геометрией:
  ранг = красное по ВСЕМУ периметру (>=3 рёбер); X = красное в 1 углу.

Режимы:
  python inv_probe.py            — живой лог классификации (раз в ~1.2с)
  python inv_probe.py --dump     — один проход + сохранить кропы слотов в crops/
                                   (для офлайн-разбора рамок / индикатора блокировки)

Стоп: F12 / Ctrl+C.
"""
import json
import os
import sys
import time
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import numpy as np
import cv2
import mss
import pyautogui
import pygetwindow as gw

DUMP = "--dump" in sys.argv

try:
    import keyboard

    def wait_f8():
        while True:
            ev = keyboard.read_event()
            if ev.event_type == "down":
                if ev.name == "esc":
                    print("Отмена."); sys.exit(1)
                if ev.name == "f8":
                    time.sleep(0.25); return

    def kill():
        try:
            return keyboard.is_pressed("f12")
        except Exception:
            return False
except Exception:
    def wait_f8():
        input("  [keyboard недоступен] клик в окно + Enter...")

    def kill():
        return False

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
INV = CFG["inventory"]
ICAL = os.path.join(HERE, "inv_calibration.json")
CROPS = os.path.join(HERE, "crops")

BORDER_FRAC = INV.get("border_frac", 0.22)   # толщина кольца-рамки от размера ячейки
RED_RING_MIN = INV.get("red_ring_min", 0.30)  # доля красного по кольцу => красный ранг
RED_EDGES_MIN = INV.get("red_edges_min", 3)   # сколько рёбер красные => ранг (иначе X)


def find_window():
    for w in gw.getAllWindows():
        t = w.title or ""
        if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
            return w
    return None


def calibrate(win):
    print("=== Калибровка сетки инвентаря ===")
    print(f"Сетка {INV['cols']}x{INV['rows']} (cols x rows из config).")
    pts = {}
    print("\n[ЛЕВ-ВЕРХ] наведи на ЦЕНТР левой-верхней ячейки инвентаря, F8")
    wait_f8(); x, y = pyautogui.position()
    pts["tl"] = {"rx": (x - win.left) / win.width, "ry": (y - win.top) / win.height}
    print(f"  OK ({x},{y})")
    print("\n[ПРАВ-НИЗ] наведи на ЦЕНТР правой-нижней ячейки инвентаря, F8")
    wait_f8(); x, y = pyautogui.position()
    pts["br"] = {"rx": (x - win.left) / win.width, "ry": (y - win.top) / win.height}
    print(f"  OK ({x},{y})")
    json.dump({"points": pts}, open(ICAL, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Сохранено: {ICAL}")
    return pts


def centers(win, pts):
    tl, br = pts["tl"], pts["br"]
    cols, rows = INV["cols"], INV["rows"]
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            fx = c / (cols - 1) if cols > 1 else 0.0
            fy = r / (rows - 1) if rows > 1 else 0.0
            rx = tl["rx"] + (br["rx"] - tl["rx"]) * fx
            ry = tl["ry"] + (br["ry"] - tl["ry"]) * fy
            row.append((win.left + rx * win.width, win.top + ry * win.height))
        out.append(row)
    return out


def cell_pitch(win, pts):
    """Шаг сетки в px (расстояние между центрами соседних ячеек)."""
    tl, br = pts["tl"], pts["br"]
    cols, rows = INV["cols"], INV["rows"]
    dx = abs(br["rx"] - tl["rx"]) * win.width / max(cols - 1, 1)
    dy = abs(br["ry"] - tl["ry"]) * win.height / max(rows - 1, 1)
    return dx, dy


HUE_RANKS = [
    (35, 85, "uncommon"),    # зелёный
    (86, 128, "rare"),       # синий
    (129, 160, "epic"),      # фиолет
    (10, 34, "legendary"),   # оранж/золото
]


def hue_to_rank(hue):
    for lo, hi, name in HUE_RANKS:
        if lo <= hue <= hi:
            return name
    return "legendary"  # 161-170 хвост к золоту/красному — крайне редко


def analyze(img):
    """Классификация слота по кольцу-рамке.

    Вернуть dict: rank, hue, n_ring, red_frac, red_edges, base_rank.
    Красный РАНГ = красное по >=RED_EDGES_MIN рёбрам И доля >= RED_RING_MIN.
    Угловой X = красное в 1 углу: игнор, ранг по не-красному кольцу.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    h, w = H.shape
    bw = max(2, int(min(h, w) * BORDER_FRAC))

    sat = (S > INV["border_sat_min"]) & (V > INV["border_val_min"])
    red = (H < 10) | (H > 170)

    ring = np.zeros((h, w), bool)
    ring[:bw, :] = True; ring[-bw:, :] = True
    ring[:, :bw] = True; ring[:, -bw:] = True

    edges = {
        "T": (slice(0, bw), slice(None)),
        "B": (slice(h - bw, h), slice(None)),
        "L": (slice(None), slice(0, bw)),
        "R": (slice(None), slice(w - bw, w)),
    }
    ring_sat = ring & sat
    n_ring = int(ring_sat.sum())

    # красное по рёбрам
    red_edges = 0
    for sl in edges.values():
        e_sat = sat[sl]
        e_red = red[sl] & sat[sl]
        if e_sat.sum() > 0 and e_red.sum() / max(e_sat.sum(), 1) > 0.30:
            red_edges += 1
    red_frac = float((ring & red & sat).sum()) / max(n_ring, 1)

    # базовый ранг по НЕ-красному кольцу
    base_mask = ring & sat & ~red
    n_base = int(base_mask.sum())
    base_hue = float(np.median(H[base_mask])) if n_base >= INV["min_color_pixels"] else -1
    base_rank = hue_to_rank(base_hue) if base_hue >= 0 else "common"

    # решение
    if red_edges >= RED_EDGES_MIN and red_frac >= RED_RING_MIN:
        rank, hue = "red", float(np.median(H[ring & red & sat])) if (ring & red & sat).any() else 5.0
    elif n_base >= INV["min_color_pixels"]:
        rank, hue = base_rank, base_hue
    else:
        rank, hue = "common", -1

    return {"rank": rank, "hue": hue, "n_ring": n_ring, "red_frac": round(red_frac, 2),
            "red_edges": red_edges, "base_rank": base_rank, "base_hue": round(base_hue, 1)}


SHORT = {"common": ".", "uncommon": "G", "rare": "B", "epic": "P",
         "legendary": "L", "red": "R"}


def main():
    win = find_window()
    if not win:
        print("Окно игры не найдено."); sys.exit(1)
    print(f"Окно: {win.title!r}")
    if os.path.exists(ICAL):
        pts = json.load(open(ICAL, encoding="utf-8"))["points"]
        print(f"Загрузил {ICAL}. (Удали файл, чтобы перекалибровать сетку.)")
    else:
        pts = calibrate(win)

    dx, dy = cell_pitch(win, pts)
    # замер: кольцо берём с почти полной ячейки (рамка живёт на краю)
    cw = max(int(dx * 0.95), 20)
    ch = max(int(dy * 0.95), 20)
    # dump: чуть шире, чтобы рамка и угловые значки/замок попали целиком
    dw = max(int(dx * 1.10), 24)
    dh = max(int(dy * 1.10), 24)

    lock = set(INV["lock_ranks"])
    print(f"\nЗамер-кольцо {cw}x{ch}px, рамка {int(min(cw,ch)*BORDER_FRAC)}px. Лочить: {sorted(lock)}")
    print("Легенда: .=обычн/пусто G=зелён B=синий P=фиолет L=золото R=КРАСНЫЙ")
    print("[*] = попало бы под блокировку.\n")

    if DUMP:
        os.makedirs(CROPS, exist_ok=True)
        run_dump(win, pts, dw, dh, lock)
        return

    with mss.mss() as sct:
        while True:
            if kill():
                print("F12 — стоп."); break
            win = find_window()
            if not win:
                time.sleep(1); continue
            grid = centers(win, pts)
            lines, detail = [], []
            for r, row in enumerate(grid):
                cells = []
                for c, (cx, cy) in enumerate(row):
                    img = np.array(sct.grab({"left": int(cx - cw / 2), "top": int(cy - ch / 2),
                                             "width": cw, "height": ch}))[:, :, :3]
                    a = analyze(img)
                    mark = "*" if a["rank"] in lock else " "
                    cells.append(f"{SHORT[a['rank']]}{mark}")
                    if a["rank"] != "common":
                        detail.append(f"r{r}c{c}:{a['rank']}(h{int(a['hue'])},"
                                      f"redE{a['red_edges']},rf{a['red_frac']})")
                lines.append(" ".join(cells))
            print("--- инвентарь ---")
            for ln in lines:
                print("  " + ln)
            if detail:
                print("  " + " | ".join(detail))
            time.sleep(1.2)


def run_dump(win, pts, dw, dh, lock):
    """Один проход: сохранить кроп каждого слота в crops/ + отчёт."""
    grid = centers(win, pts)
    report = []
    saved = 0
    with mss.mss() as sct:
        for r, row in enumerate(grid):
            for c, (cx, cy) in enumerate(row):
                img = np.array(sct.grab({"left": int(cx - dw / 2), "top": int(cy - dh / 2),
                                         "width": dw, "height": dh}))[:, :, :3]
                a = analyze(img)
                fn = f"r{r}c{c}_{a['rank']}.png"
                cv2.imwrite(os.path.join(CROPS, fn), img)
                saved += 1
                report.append(f"{fn}: rank={a['rank']} hue={int(a['hue'])} "
                              f"base={a['base_rank']}(h{a['base_hue']}) "
                              f"redEdges={a['red_edges']} redFrac={a['red_frac']} nRing={a['n_ring']}")
    open(os.path.join(CROPS, "_report.txt"), "w", encoding="utf-8").write("\n".join(report))
    print(f"DUMP: сохранено {saved} кропов в {CROPS}")
    print("Отчёт: crops/_report.txt")
    for ln in report:
        print("  " + ln)


if __name__ == "__main__":
    main()
