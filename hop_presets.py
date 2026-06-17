"""hop_presets.py — библиотека пресетов хопа: готовые community-стратегии + именованные
кастомные маршруты юзера. WIP, тест офлайн (test_hop_presets.py).

Пресет — это ТОНКИЙ слой удобства поверх контракта `config.hop` (enabled/mode/difficulty/
max_ahead/hero_level/route). Выбор пресета не меняет рантайм (farm2._init_hop читает config.hop
как раньше) — он лишь ЗАПОЛНЯЕТ поля вкладки Stage hop. Значит ядро (жив-проверенная навигация,
runtracker-тайминг) остаётся нетронутым.

Два рода пресетов (`kind`):
  • "strategy" — конфиг событийного juggling (hopmode/hopper): mode=strategy + difficulty/max_ahead.
    Прыгает только когда босс убит + сундук забран → таймеры угадывать не надо, безопасно.
  • "route"    — таймерный маршрут (routehop): mode=route + список этапов с временем стоянки.
    Кастомные пресеты юзера = это (фиксированные stops). Community-маршрут может ГЕНЕРИТЬСЯ под
    уровень героя (`generate` → routehop.suggest_route), т.к. безопасный пул этапов зависит от ростера.

Community-пресеты — код-константы (ниже). Кастомные — в hop_presets.json (отдельно от config.json,
переживают сброс конфига). Имена community зарезервированы (add_user их отклоняет).

🚫 Бан-безопасность наследуется: пресеты только выбирают этапы/время, навигация — легит клики
(stagenav). Уровневое окно (hopper.level_window) защищает от EXP-штрафа и непроходимых стадий.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS_PATH = os.path.join(HERE, "hop_presets.json")

# ── Community-пресеты (встроенные, под фактами F1–F13 и правилом «не >8 ур выше героя») ──────────
COMMUNITY = [
    {
        "name": "Level-window circuit",
        "kind": "strategy",
        "difficulty": None,            # any — весь уровневый пул
        "max_ahead": 8,
        "description": "Event-driven juggling across every stage within your level window. "
                       "Hops only after the boss is killed and its chest is secured. Safest "
                       "general default — no timing guesses.",
    },
    {
        "name": "Single-difficulty sweep",
        "kind": "strategy",
        "difficulty": None,            # юзер выбирает сложность в UI (needs_difficulty)
        "max_ahead": 8,
        "needs_difficulty": True,
        "description": "Same juggling but locked to ONE difficulty = fewer PORTAL clicks per hop "
                       "(no difficulty-dropdown switching). Pick a difficulty below before saving.",
    },
    {
        "name": "Safe (at-level only)",
        "kind": "strategy",
        "difficulty": None,
        "max_ahead": 0,
        "description": "Never routes a stage above your hero level. For rosters that stall on tough "
                       "mechanics (e.g. fire elementals on 2-8). Zero EXP-penalty risk.",
    },
    {
        "name": "Auto timed circuit",
        "kind": "route",
        "generate": {"n": 4, "dwell_sec": 240, "max_ahead": 8},
        "description": "Builds a fixed timed map of 4 different-level stages (~4 min each) inside "
                       "your level window. Edit the per-stage times after filling.",
    },
]

_COMMUNITY_NAMES = {p["name"] for p in COMMUNITY}


def community():
    """Встроенные пресеты (копии, чтобы вызывающий их не мутировал)."""
    return [dict(p) for p in COMMUNITY]


# ── Кастомная библиотека юзера (hop_presets.json) ───────────────────────────────────────────────
def load_user(path=PRESETS_PATH):
    """Список кастомных пресетов юзера [{name, kind:'route', stops:[...]}, ...]. Нет файла/битый → []."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    presets = data.get("presets", []) if isinstance(data, dict) else data
    out = []
    for p in presets or []:
        if isinstance(p, dict) and p.get("name") and isinstance(p.get("stops"), list):
            out.append({"name": str(p["name"]).strip(), "kind": "route",
                        "stops": [dict(s) for s in p["stops"]]})
    return out


def save_user(presets, path=PRESETS_PATH):
    """Перезаписать библиотеку юзера."""
    clean = [{"name": p["name"], "kind": "route", "stops": p["stops"]} for p in presets]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "presets": clean}, f, ensure_ascii=False, indent=2)


def add_user(name, stops, path=PRESETS_PATH):
    """Сохранить/заменить кастомный маршрут под именем. Возвращает (ok, msg).
    Отклоняет: пустое имя, имя community (зарезервировано), пустой маршрут.
    Совпадение с существующим кастомным именем → перезапись (update)."""
    name = (name or "").strip()
    if not name:
        return False, "name is empty"
    if name in _COMMUNITY_NAMES:
        return False, f"'{name}' is a built-in preset name — pick another"
    if not stops:
        return False, "route is empty — add stages first"
    presets = [p for p in load_user(path) if p["name"] != name]
    presets.append({"name": name, "kind": "route", "stops": [dict(s) for s in stops]})
    presets.sort(key=lambda p: p["name"].lower())
    save_user(presets, path)
    return True, f"saved '{name}'"


def delete_user(name, path=PRESETS_PATH):
    """Удалить кастомный пресет. Возвращает (ok, msg). Community удалить нельзя."""
    name = (name or "").strip()
    if name in _COMMUNITY_NAMES:
        return False, f"'{name}' is built-in — cannot delete"
    presets = load_user(path)
    kept = [p for p in presets if p["name"] != name]
    if len(kept) == len(presets):
        return False, f"no custom preset named '{name}'"
    save_user(kept, path)
    return True, f"deleted '{name}'"


# ── Объединённый доступ + применение ────────────────────────────────────────────────────────────
def all_presets(path=PRESETS_PATH):
    """Community + кастомные. Каждый помечен 'builtin' (True/False). Community идут первыми."""
    out = [dict(p, builtin=True) for p in community()]
    out += [dict(p, builtin=False) for p in load_user(path)]
    return out


def get(name, path=PRESETS_PATH):
    """Пресет по имени (community имеет приоритет). None если нет."""
    name = (name or "").strip()
    for p in community():
        if p["name"] == name:
            return p
    for p in load_user(path):
        if p["name"] == name:
            return p
    return None


def apply(preset, hero_level, difficulty=None):
    """ЧИСТО: пресет → патч полей вкладки Stage hop (UI применяет присутствующие ключи).
    Ключи: mode ('strategy'|'route'), [difficulty], [max_ahead], [route_stops], [warn], hint.
    Контракт config.hop не расширяется — только заполнение существующих полей."""
    kind = preset.get("kind", "strategy")
    out = {"mode": "route" if kind == "route" else "strategy",
           "hint": preset.get("description", "")}
    if "max_ahead" in preset:
        out["max_ahead"] = int(preset["max_ahead"])
    if preset.get("difficulty") is not None:
        out["difficulty"] = preset["difficulty"]
    if kind == "route":
        if preset.get("stops") is not None:
            out["route_stops"] = [dict(s) for s in preset["stops"]]
        elif preset.get("generate"):
            import routehop
            g = preset["generate"]
            out["route_stops"] = routehop.suggest_route(
                hero_level, difficulty=difficulty, n=int(g.get("n", 4)),
                dwell_sec=int(g.get("dwell_sec", 240)), max_ahead=int(g.get("max_ahead", 8)))
    if preset.get("needs_difficulty") and not difficulty:
        out["warn"] = "this preset wants a single difficulty — pick one above"
    return out


if __name__ == "__main__":
    for p in all_presets():
        tag = "built-in" if p["builtin"] else "custom"
        print(f"  [{tag:8}] {p['name']:24} ({p['kind']})")
    print("apply Auto timed circuit @ L65 NIGHTMARE:")
    patch = apply(get("Auto timed circuit"), 65, "NIGHTMARE")
    print("  mode:", patch["mode"], " stops:",
          [s["label"] for s in patch.get("route_stops", [])])
