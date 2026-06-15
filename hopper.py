"""hopper.py — планировщик «прыжков по стадиям» (chest-juggling). WIP, НЕ интегрирован в farm2.

Идея (подтверждена сообществом @taskbarhero + Денис): КД сундука считается ПО УРОВНЮ стадии,
поэтому если просто прыгать по РАЗНЫМ стадиям (разные уровни) — у каждого уровня свой КД и сундуки
капают почти непрерывно. Сложные таймеры не нужны: достаточно рандом-перебора стадий, избегая
повтора недавних уровней. См. память tbh-chest-stage-strategy.

🚫 Бан-риск: НИКОГДА не обходить КД реконнектом/перезаходом игры. Тут только выбор стадий —
исполнение (клики по PORTAL) и навигация будут в stagenav.py поверх этого планировщика.

Чистая логика, без игры/сети → тестируется офлайн (test_hopper.py). Данные: gamedb/stages_nav.json
(label «сложность-акт-этап», level, name, boss, exp/gold per clear).
"""
import os
import json
import random

HERE = os.path.dirname(os.path.abspath(__file__))
NAV_PATH = os.path.join(HERE, "gamedb", "stages_nav.json")


def load_nav(path=NAV_PATH):
    """Список этапов с навигационными метаданными (label, level, act, no, difficulty, ...)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def by_label(stages, label):
    for s in stages:
        if s.get("label") == label:
            return s
    return None


def level_window(stages, hero_level, max_ahead=8, max_behind=None):
    """Этапы, безопасные по EXP-штрафу: уровень этапа не выше hero_level+max_ahead (правило «не
    убегать >8 уровней», пин сообщества). max_behind — отсечь слишком низкие (трата времени)."""
    out = []
    for s in stages:
        lv = s.get("level")
        if lv is None:
            continue
        if lv > hero_level + max_ahead:
            continue
        if max_behind is not None and lv < hero_level - max_behind:
            continue
        out.append(s)
    return out


def cluster(stages, difficulty=None, act=None):
    """Сузить до одной сложности/акта — чтобы хоп требовал меньше навигации в PORTAL (не дёргать
    дропдаун сложности и табы актов каждый прыжок). difficulty: NORMAL/NIGHTMARE/HELL/TORMENT."""
    out = stages
    if difficulty:
        out = [s for s in out if s.get("difficulty") == difficulty]
    if act is not None:
        out = [s for s in out if s.get("act") == act]
    return out


def next_stage(pool, recent_levels, rng):
    """Случайный этап из pool, избегая уровней из recent_levels (чтобы КД был свежим). Если все
    отфильтровались — берём из полного pool. rng = random.Random (для детерминизма в тестах)."""
    if not pool:
        return None
    fresh = [s for s in pool if s.get("level") not in set(recent_levels)]
    return rng.choice(fresh or pool)


def plan_hops(pool, n, seed=0, avoid_recent=3):
    """Последовательность из n этапов для хопа: без повтора уровня в пределах последних
    avoid_recent шагов (рандом-перебор с разнесением уровней). Детерминирована по seed."""
    if not pool:
        return []
    rng = random.Random(seed)
    seq, recent = [], []
    for _ in range(n):
        s = next_stage(pool, recent[-avoid_recent:], rng)
        seq.append(s)
        recent.append(s.get("level"))
    return seq


def hop_pair(pool, seed=0):
    """Пара этапов РАЗНЫХ уровней (минимальный juggling A/B). None если нет двух разных уровней."""
    levels = {}
    for s in pool:
        levels.setdefault(s.get("level"), s)
    uniq = list(levels.values())
    if len(uniq) < 2:
        return None
    rng = random.Random(seed)
    return tuple(rng.sample(uniq, 2))


if __name__ == "__main__":
    st = load_nav()
    print(f"stages: {len(st)}  levels {min(s['level'] for s in st)}–{max(s['level'] for s in st)}")
    pool = level_window(st, hero_level=65, max_ahead=8)
    print(f"pool for hero L65 (+8): {len(pool)} stages, labels:",
          ", ".join(s["label"] for s in pool[:12]), "…")
    seq = plan_hops(pool, 8, seed=1)
    print("sample hop plan:", " -> ".join(f"{s['label']}(L{s['level']})" for s in seq))
