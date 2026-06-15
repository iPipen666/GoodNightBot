"""state.py — count-first ассессор: по счётчикам заполнения выбирает одно действие."""

import json
import os
import time
from collections import namedtuple

import farm
import mss
import vision

# --- константы модуля ---
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
INV = CFG["inventory"]
STATE = CFG.get("state", {})


def reload_config():
    """Перечитать config.json в рантайме (настройки панели без рестарта)."""
    global CFG, INV, STATE
    CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    INV = CFG["inventory"]
    STATE = CFG.get("state", {})

# --- структура действия ---
Action = namedtuple("Action", ["kind", "reason", "data"])
# kind   : str — "merge" | "save_sort" | "open_chest" | "idle"
# reason : str — человекочитаемая русская строка для лога
# data   : dict — доп. поля для исполнителя


def assess(sct, ctx) -> Action:
    """Один detect + один inv_fill → первое сработавшее правило по приоритету."""
    farm.ensure_inventory_tab(sct)   # HERO на вкладку Inventory, иначе счёт читает ростер
    win, panels = farm.detect(sct)
    inv = farm.inv_fill(sct)
    cap = INV["cols"] * INV["rows"]

    # пороги из конфига (с дефолтами)
    save_inv_threshold = STATE.get("save_inv_threshold", 34)
    merge_inv_min = STATE.get("merge_inv_min", 9)
    chest_every_cycles = STATE.get("chest_every_cycles", 3)
    save_every_cycles = STATE.get("save_every_cycles", 2)

    # ctx читаем через .get (все поля опциональны)
    cycles_since_chest = ctx.get("cycles_since_chest", 0)
    cycles_since_save = ctx.get("cycles_since_save", 0)

    # 1) принудительная разгрузка при переполнении
    if inv >= 0 and inv >= save_inv_threshold:
        return Action(
            "save_sort",
            f"инвентарь {inv}/{cap} — разгрузка",
            {"inv": inv},
        )

    # 1.5) ПОЧТА по таймеру (раз в mail_every_sec): открыть -> обновить -> получить все
    if STATE.get("mail_enabled", True) and \
            time.time() - ctx.get("last_mail_ts", 0) >= STATE.get("mail_every_sec", 330):
        return Action("mail", "проверка почты (по таймеру)", {})

    # 2) СУНДУКИ по таймеру — ПРИОРИТЕТ (иначе при постоянном мерже сундуки голодают и
    #    переполняются: куб остаётся открыт, мерж перехватывал бы каждый цикл). Space
    #    открывает все сундуки и сворачивает панели (закрывает куб) — это разрывает merge-залип.
    if cycles_since_chest >= chest_every_cycles:
        return Action(
            "open_chest",
            "пора открыть сундуки",
            {},
        )

    # 3) плановая раскладка стэша по таймеру (инвентарь -> стэш + сортировка)
    if cycles_since_save >= save_every_cycles:
        return Action(
            "save_sort",
            "плановая раскладка стэша",
            {"inv": inv},
        )

    # 4) Мерж — но НЕ долбить куб каждый цикл, если мержить нечего. После пустого мержа
    #    (0 наборов) _do_merge ставит merge_cooldown: стэш/инвентарь без мержабельных
    #    предметов (напр. всё Бессмертное/красное) -> ждём пока фарм нанесёт свежий лут,
    #    а не открываем куб впустую. Кулдаун декрементится в цикле farm2.
    if ctx.get("merge_cooldown", 0) > 0:
        return Action(
            "idle",
            f"мержить нечего — жду лут (кулдаун {ctx['merge_cooldown']})",
            {},
        )
    # pre-scan «анализ перед мержем»: открываем куб ТОЛЬКО если в инвентаре есть свежий
    # мержабельный лут. Пусто / только epic-red -> в стэше остатки <9 на тип, новый сет
    # не сложится -> idle, куб не трогаем. hero не виден -> -1 -> пробуем (кулдаун бэкстопит).
    hero = panels.get("hero")
    mg = farm.count_mergeable(sct, hero) if hero else -1
    if mg == 0:
        return Action("idle", "в инвентаре нет мержабельного — жду лут", {})
    return Action(
        "merge",
        f"мержабельных в инвентаре: {mg if mg >= 0 else '?'} — мерж",
        {"inv": inv},
    )
