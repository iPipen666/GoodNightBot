"""calib_steps.py — шаги ВСТРОЕННОГО мастера калибровки (точки + русские подсказки).

Чистая логика (без Tk/игры): список шагов + сборка файла калибровки из снятых точек. Сам захват
точки (курсор + F8) живёт в control.py (мастер в окне панели, не в консоли).

Шаг: kind='point' — снять точку (навести курсор в игре + F8); kind='instruct' — просто инструкция
(кнопка «далее»). field — куда писать точку; node=(page,no) — узел карты этапов.
"""

def _nodes(prompt_page, page, nums):
    return [{"kind": "point", "node": (page, n),
             "text": f"Узел этапа {n} ({prompt_page})."} for n in nums]


PORTAL_STEPS = [
    {"kind": "point", "field": "diff_dropdown",
     "text": "Наведи курсор на ДРОПДАУН СЛОЖНОСТИ (надпись вверху карты, напр. «Мучение ▾»)."},
    {"kind": "instruct",
     "text": "Кликни по дропдауну в игре, чтобы он РАСКРЫЛСЯ (видны Обычный/Кошмар/Ад/Мучение). "
             "Готово — жми «далее»."},
    {"kind": "point", "field": "diff_option_normal", "text": "Наведи на опцию «Обычный»."},
    {"kind": "point", "field": "diff_option_nightmare", "text": "Наведи на опцию «Кошмар»."},
    {"kind": "point", "field": "diff_option_hell", "text": "Наведи на опцию «Ад»."},
    {"kind": "point", "field": "diff_option_torment", "text": "Наведи на опцию «Мучение»."},
    {"kind": "point", "field": "act_tab_1", "text": "Наведи на таб «Акт 1»."},
    {"kind": "point", "field": "act_tab_2", "text": "Наведи на таб «Акт 2»."},
    {"kind": "point", "field": "act_tab_3", "text": "Наведи на таб «Акт 3»."},
    {"kind": "point", "field": "scroll_anchor",
     "text": "Наведи на ЦЕНТР карты этапов (над этой точкой бот крутит колесо)."},
    {"kind": "instruct",
     "text": "Прокрути карту колесом в САМЫЙ НИЗ. Дальше снимем нижние этапы 1→7 (на пройденном Акте 1)."},
    *_nodes("низ карты", "bottom", range(1, 8)),
    {"kind": "instruct",
     "text": "Теперь прокрути карту в САМЫЙ ВЕРХ. Снимем верхние этапы 10→8."},
    *_nodes("верх карты", "top", (10, 9, 8)),
]

STEPS = {"portal": PORTAL_STEPS}


def step_id(step):
    if step.get("field"):
        return step["field"]
    if step.get("node"):
        p, n = step["node"]
        return f"node:{p}:{n}"
    return None


def point_steps(target):
    return [s for s in STEPS[target] if s["kind"] == "point"]


def to_fraction(x, y, win):
    """Экранная точка → доли окна игры (как в калибраторах)."""
    return {"rx": round((x - win.left) / win.width, 4),
            "ry": round((y - win.top) / win.height, 4)}


def build_portal(captures, win):
    """captures: {step_id: {rx,ry}} → словарь portal_calibration.json (+ calib_window)."""
    cal, nb, nt = {}, [], []
    for s in PORTAL_STEPS:
        if s["kind"] != "point":
            continue
        pt = captures.get(step_id(s))
        if not pt:
            continue
        if s.get("field"):
            cal[s["field"]] = pt
        else:
            page, no = s["node"]
            (nb if page == "bottom" else nt).append({"no": no, "rx": pt["rx"], "ry": pt["ry"]})
    if nb:
        cal["nodes_bottom"] = sorted(nb, key=lambda d: d["no"])
    if nt:
        cal["nodes_top"] = sorted(nt, key=lambda d: d["no"])
    cal["calib_window"] = {"w": int(win.width), "h": int(win.height)}
    return cal


BUILDERS = {"portal": build_portal}
