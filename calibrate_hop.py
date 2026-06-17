r"""calibrate_hop.py — F8-калибратор навигации PORTAL (ручные клики Дениса).

Две группы точек:
  • ФИКСИРОВАННЫЕ (дропдаун сложности, 4 опции, табы Акт1/2/3) — banner-relative (offset от центра
    баннера PORTAL / ширину баннера). Не зависят от скролла. → offsets.json["portal"].
  • УЗЛЫ этапов — относительно ЗЕЛЁНОГО КОЛЬЦА (текущий этап). Карта центрируется на текущем этапе,
    поэтому смещение «узел этапа (тек+d) от кольца» постоянно. Калибруем по ДЕЛЬТЕ d. → hop_nodes.json
    {"d": [ox,oy]} (offset от кольца / ширину баннера). Навигация: клик = кольцо + offset[target-cur].

Запуск (PORTAL открыт, зелёное кольцо видно):
  .\.venv\Scripts\python.exe calibrate_hop.py
Управление: наводишь курсор + F8 снять · S пропустить · Esc выход.
Боссы [*-10] (красные) НЕ калибруем — на них не прыгаем.
"""
import json
import os
import sys
import time

import logwatch
import vision

HERE = os.path.dirname(os.path.abspath(__file__))
OFFS = os.path.join(HERE, "offsets.json")
NODES = os.path.join(HERE, "hop_nodes.json")


def _wait():
    import keyboard
    while True:
        ev = keyboard.read_event()
        if ev.event_type == "down":
            if ev.name == "esc":
                return "quit"
            if ev.name == "s":
                return "skip"
            if ev.name == "f8":
                time.sleep(0.12); return "ok"


def _banner():
    import mss
    w = logwatch.find_game_window()
    if not w:
        print("❌ окно игры не найдено"); sys.exit(1)
    sct = mss.MSS()
    b = vision.detect(w, sct, names=["portal"]).get("portal")
    if not b:
        print("❌ PORTAL не открыт — открой карту и перезапусти"); sys.exit(1)
    return w, sct, b


def _cursor():
    import pyautogui
    return pyautogui.position()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    w, sct, b = _banner()
    print(f"PORTAL баннер: центр=({int(b['cx'])},{int(b['cy'])}) ширина={int(b['w'])}")

    off = {}
    try:
        off = json.load(open(OFFS, encoding="utf-8"))
    except Exception:
        pass
    psec = off.setdefault("portal", {})

    print("\n=== ФИКСИРОВАННЫЕ КНОПКИ (banner-relative) ===")
    fixed = [
        ("diff_dropdown", "ДРОПДАУН сложности (надпись «Кошмар ▾» вверху)"),
        ("@msg", "Кликни по дропдауну, чтобы РАСКРЫЛСЯ (видны Обычный/Кошмар/Ад/Мучение)"),
        ("diff_option_normal", "опция «Обычный»"),
        ("diff_option_nightmare", "опция «Кошмар»"),
        ("diff_option_hell", "опция «Ад»"),
        ("diff_option_torment", "опция «Мучение»"),
        ("act_tab_1", "таб «Акт 1»"),
        ("act_tab_2", "таб «Акт 2»"),
        ("act_tab_3", "таб «Акт 3»"),
    ]
    for key, prompt in fixed:
        if key == "@msg":
            input(f"  ▸ {prompt}\n    Enter когда готово…"); continue
        print(f"  ▸ {prompt}\n      [F8 снять · S пропустить · Esc выход]")
        a = _wait()
        if a == "quit":
            break
        if a == "skip":
            print("      (пропущено)"); continue
        x, y = _cursor()
        b = vision.detect(w, sct, names=["portal"]).get("portal") or b   # свежий баннер
        ox, oy = vision.norm_offset(b, x, y)
        psec[key] = [round(ox, 4), round(oy, 4)]
        json.dump(off, open(OFFS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"      ✓ {key} = [{psec[key][0]}, {psec[key][1]}]")

    print("\n=== УЗЛЫ ЭТАПОВ (относительно ТЕКУЩЕГО = зелёного кольца) ===")
    cur = input("На каком этапе ты СЕЙЧАС (где зелёное кольцо)? номер 1-10: ").strip()
    try:
        cur_no = int(cur)
    except ValueError:
        print("не число — пропускаю узлы"); cur_no = None

    nodes = {}
    try:
        nodes = json.load(open(NODES, encoding="utf-8"))
    except Exception:
        pass

    if cur_no is not None:
        print("  ▸ наведи на ЦЕНТР ЗЕЛЁНОГО КОЛЬЦА (текущий этап) + F8")
        a = _wait()
        if a == "ok":
            ring = _cursor()
            print(f"    ✓ кольцо (этап {cur_no}) в {ring}")
            print("Теперь каждый этап: наведи на белый кружок + F8, потом введи его номер.")
            print("Сними соседние (1..9), КРАСНЫЙ [*-10] пропусти. S/Esc — закончить.")
            b = vision.detect(w, sct, names=["portal"]).get("portal") or b
            while True:
                print("  ▸ наведи на УЗЕЛ (белый кружок) + F8 (S=хватит, Esc=выход)")
                a = _wait()
                if a in ("skip", "quit"):
                    break
                x, y = _cursor()
                lab = input("    номер этапа этого узла (1-10): ").strip()
                try:
                    no = int(lab)
                except ValueError:
                    print("    не число — пропуск"); continue
                d = no - cur_no
                ox = round((x - ring[0]) / b["w"], 4)
                oy = round((y - ring[1]) / b["w"], 4)
                nodes[str(d)] = [ox, oy]
                json.dump(nodes, open(NODES, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                print(f"    ✓ дельта {d:+d} = [{ox}, {oy}]  (узлов: {len(nodes)})")

    print(f"\n💾 offsets.json[portal]: {len([k for k in psec])} точек · hop_nodes.json: {len(nodes)} дельт")
    try:
        input("Enter — закрыть.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
