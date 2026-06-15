"""test_chest_color.py — классификация типа сундука по ЦВЕТУ ТЕКСТА строки лога (юзер подтвердил
палитру: серый=обычный, синий=этапа, красный=акта). Надёжнее обрезаемого маркизой текста.
Строим синтетические патчи (тёмная пилюля + яркий цветной 'текст') и проверяем chest_kind_by_color."""
import sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
import logwatch

fails = []
def check(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name)
    if not cond:
        fails.append(name)


def patch(rgb, bg=(18, 16, 20), w=120, h=20, txt_frac=0.35):
    """Пилюля: тёмный фон + строка ярких пикселей цвета rgb (имитация текста)."""
    a = np.zeros((h, w, 3), dtype="int16")
    a[:, :] = bg
    ncols = int(w * txt_frac)
    # раскидать 'текст' по строке (несколько вертикальных штрихов)
    for i in range(ncols):
        x = int(i * (w / ncols))
        a[h // 4: 3 * h // 4, x] = rgb
    return a, (0, 0, w - 1, h - 1)


# значения замерены живьём (ядро текста lum>180 на чистом участке)
GRAY = (237, 237, 237)     # обычный сундук — серый
WHITE = (240, 240, 239)
BLUE = (183, 223, 247)     # синий boss-текст ЯРКИЙ (замер живьём, lum=217, B-R=64)
BLUE2 = (190, 218, 248)
RED = (236, 92, 88)        # красный act-текст (тусклее, lum~139 → ловится в средней полосе)
RED2 = (220, 80, 78)

for name, rgb, want in [
    ("серый → normal", GRAY, "normal"),
    ("белый → normal", WHITE, "normal"),
    ("синий → stage_boss", BLUE, "stage_boss"),
    ("синий2 → stage_boss", BLUE2, "stage_boss"),
    ("красный → act_boss", RED, "act_boss"),
    ("красный2 → act_boss", RED2, "act_boss"),
]:
    arr, box = patch(rgb)
    got = logwatch.chest_kind_by_color(arr, box)
    check(f"{name} (got={got})", got == want)

# пустой/тёмный бокс → None (нет текста, не выдумываем тип)
arr = np.full((20, 120, 3), 18, dtype="int16")
check("тёмный бокс без текста → None", logwatch.chest_kind_by_color(arr, (0, 0, 119, 19)) is None)

print("\n" + ("ВСЕ ОК" if not fails else f"ПРОВАЛЫ: {fails}"))
sys.exit(1 if fails else 0)
