"""calibration.py — ЕДИНЫЙ реестр всех калибровок бота + статус-гейт. WIP, тест офлайн.

Бот ориентируется в игре двумя системами координат:
  • banner_relative (offsets.json) — смещения, нормированные на ширину детектируемого баннера панели
    → ПОРТАТИВНО (масштаб/позиция/разрешение не ломают). Север-стар проекта: достаточно наличия файла.
  • window_fraction (доли окна rx,ry) — снято на КОНКРЕТНОМ окне → НЕпортативно. Валидно только на окне
    того же размера. Каждый такой файл несёт размер окна калибровки (calib_window {w,h} или
    win_rect_at_cal). ГЕЙТ не даёт кликать на чужом/изменённом окне (иначе промахи по UI) — юзер
    калибрует 1 раз под своё окно (обязательный first-run).

Реестр перечисляет ЖИВЫЕ калибровки. Легаси inv/stash/auto/panel_toggles читаются только _attic — НЕ
включены. boxes_calibration.json — это vision-ТЮНИНГ (пороги/масштабы), не клик-точки → не гейтим.

API: status(item,win) → (ok|missing|window_mismatch|no_window|error, detail); status_all(win);
feature_status(feature,win); summary(win). Фичи (gates) гейтятся по худшему статусу своих калибровок.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 0.02   # допуск совпадения размера окна с калибровочным (доли окна непортативны)

# ── Реестр живых калибровок ──────────────────────────────────────────────────────────────────────
# coord: 'banner_relative' (портативно) | 'window_fraction' (нужен размер окна).
# produces: калибратор-скрипт. gates: фичи, которым нужна эта калибровка. required: нужна для базы.
# module='stagenav' → делегируем детальную проверку (узлы/опции) в stagenav.calibration_status.
ITEMS = [
    {"id": "panels", "label": "Кнопки панелей (тайник/куб/HERO/почта)",
     "file": "offsets.json", "coord": "banner_relative", "produces": "calibrate_all.py",
     "gates": ["farm", "stash", "mail", "merge"], "required": True},
    {"id": "log", "label": "Чтение лога RECORDS",
     "file": "records_calibration.json", "coord": "window_fraction", "produces": "calibrate_records.py",
     "gates": ["log", "prelock"], "required": False},
    {"id": "chest", "label": "Открытие сундуков",
     "file": "chest_calibration.json", "coord": "window_fraction", "produces": "calibrate_records.py",
     "gates": ["chest"], "required": False},
    {"id": "portal", "label": "Карта этапов PORTAL (прыжки)",
     "file": "offsets.json", "coord": "banner_relative", "produces": "calibrate_master.py",
     "gates": ["hop"], "required": False, "module": "stagenav"},
]
# cube(calibration.json) и game_settings — ЛЕГАСИ/вторичные инструменты: живой фарм их НЕ читает
# (farm.py берёт куб/тайник/почту из offsets.json banner-relative). Поэтому в гейт не входят.


def items():
    return [dict(i) for i in ITEMS]


def get(item_id):
    for i in ITEMS:
        if i["id"] == item_id:
            return dict(i)
    return None


# ── низкоуровневое ────────────────────────────────────────────────────────────────────────────────
def _load(path):
    try:
        with open(os.path.join(HERE, path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _win():
    try:
        import logwatch
        return logwatch.find_game_window()
    except Exception:
        return None


def _calib_window_size(cal):
    """Размер окна, на котором снята калибровка. None если не записан."""
    cw = cal.get("calib_window")
    if isinstance(cw, dict) and cw.get("w") and cw.get("h"):
        return int(cw["w"]), int(cw["h"])
    wr = cal.get("win_rect_at_cal")
    if isinstance(wr, dict) and wr.get("width") and wr.get("height"):
        return int(wr["width"]), int(wr["height"])
    return None


def _has_points(cal):
    pts = cal.get("points")
    if isinstance(pts, dict):
        return len(pts) > 0
    return any(isinstance(v, dict) for v in cal.values())   # файлы без обёртки 'points'


def status(item, win=None, cal=None):
    """Статус одной калибровки для ТЕКУЩЕГО окна.
    → (status, detail). status ∈ ok | missing | window_mismatch | no_window | error."""
    if item.get("module") == "stagenav":                    # портал: детальная проверка (узлы/опции)
        try:
            import stagenav
            return stagenav.calibration_status(cal, win)
        except Exception as e:
            return "error", repr(e)
    if cal is None:
        cal = _load(item["file"])
    if not cal:
        return "missing", f"{item['file']} нет/пуст — запусти {item['produces']}"
    if not _has_points(cal):
        return "missing", f"{item['file']}: нет точек — запусти {item['produces']}"
    if item["coord"] == "banner_relative":
        return "ok", "banner-relative (портативно)"
    sz = _calib_window_size(cal)
    if not sz:
        return "no_window", f"калибровка без размера окна — перекалибруй ({item['produces']})"
    if win is None:
        win = _win()
    if not win:
        return "window_mismatch", "окно игры не найдено"
    dw = abs(win.width - sz[0]) / max(1, sz[0])
    dh = abs(win.height - sz[1]) / max(1, sz[1])
    if dw > TOL or dh > TOL:
        return ("window_mismatch",
                f"окно {win.width}x{win.height} != калибровочного {sz[0]}x{sz[1]} — "
                f"перекалибруй ({item['produces']})")
    return "ok", f"окно {sz[0]}x{sz[1]}"


def status_all(win=None):
    """[{**item, 'status', 'detail'}] по каждой калибровке."""
    if win is None:
        win = _win()
    out = []
    for it in items():
        st, detail = status(it, win)
        out.append(dict(it, status=st, detail=detail))
    return out


def feature_status(feature, win=None):
    """Худший статус среди калибровок, гейтящих фичу. → (status, blocking_item_id|None, detail).
    'ok' если все калибровки фичи ok (или фича не зависит ни от одной)."""
    if win is None:
        win = _win()
    worst = ("ok", None, "")
    rank = {"ok": 0, "no_window": 1, "window_mismatch": 1, "missing": 2, "error": 3}
    for it in items():
        if feature not in it.get("gates", []):
            continue
        st, detail = status(it, win)
        if rank.get(st, 9) > rank.get(worst[0], 0):
            worst = (st, it["id"], detail)
    return worst


def feature_ready(feature, win=None):
    return feature_status(feature, win)[0] == "ok"


def start_blockers(cfg=None, win=None):
    """Калибровки, которые ДОЛЖНЫ быть ok чтобы жать START — по ВКЛЮЧЁННЫМ фичам.
    Базовый фарм всегда требует panels (offsets, портативно). Хоп (cfg.hop.enabled) требует portal.
    log/chest НЕ блокируют START (их фичи деградируют безопасно). → [(id, detail), ...] (пусто = можно)."""
    if cfg is None:
        try:
            cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
        except Exception:
            cfg = {}
    if win is None:
        win = _win()
    need = ["panels"]
    if (cfg.get("hop", {}) or {}).get("enabled"):
        need.append("portal")
    out = []
    for it in items():
        if it["id"] in need:
            st, detail = status(it, win)
            if st != "ok":
                out.append((it["id"], detail))
    return out


def summary(win=None):
    """Сводка готовности. {ready_basic, all_ok, missing[], stale[], by_id{}}.
    ready_basic = все required калибровки ok (база фарма). all_ok = вообще все ok."""
    if win is None:
        win = _win()
    rows = status_all(win)
    by_id = {r["id"]: r for r in rows}
    missing = [r["id"] for r in rows if r["status"] == "missing"]
    stale = [r["id"] for r in rows if r["status"] in ("window_mismatch", "no_window")]
    ready_basic = all(by_id[i["id"]]["status"] == "ok" for i in ITEMS if i["required"])
    all_ok = all(r["status"] == "ok" for r in rows)
    return {"ready_basic": ready_basic, "all_ok": all_ok,
            "missing": missing, "stale": stale, "by_id": by_id}


if __name__ == "__main__":
    s = summary()
    print(f"ready_basic={s['ready_basic']}  all_ok={s['all_ok']}  "
          f"missing={s['missing']}  stale={s['stale']}")
    for r in status_all():
        mark = "OK " if r["status"] == "ok" else "!! "
        print(f"  {mark}{r['id']:10} [{r['coord']:15}] {r['status']:16} {r['detail']}")
