"""routehop.py — таймерный маршрут прыжков по стадиям («кастомная карта»). WIP, тест офлайн.

В отличие от hopmode (событийный juggling — прыгаем когда босс убит+сундук забран), здесь юзер сам
задаёт МАРШРУТ построчно: метка этапа + сколько секунд на нём стоять. Бот заходит на этап, фармит
как обычно ровно N секунд, потом прыгает на следующий, по кругу. Запас по времени = пачка
гарантированно отфармливает каждый этап.

Формат строки (либеральный парс):
    3-3-9 / time: 235 sec
    3-3-9: 235
    3-3-9   235s          # комментарий
Метка X-Y-Z = сложность(1-4)-акт(1-3)-этап(1-10) (как в stagenav.parse_label). Пустые строки и
`#`-комментарии игнорируются. Кривая метка / нет времени → строка в errors, маршрут продолжает парс.

Защита: даже если время вышло В МОМЕНТ боссового сундука (runtracker == CLEARED) — хоп откладывается
на тик, пока сундук не забран (грейс), иначе потеряем сундук. Бан-обхода нет: только навигация.

Чистая логика (парс + тайминг), навигация — колбэк (stagenav.navigate). Тест офлайн → test_routehop.
"""
import re
import time as _time

import runtracker
import stagenav

_LABEL_RE = re.compile(r"(\d)\s*-\s*(\d)\s*-\s*(\d{1,2})")


def parse_line(line):
    """'3-3-9 / time: 235 sec' → ({'label':'3-3-9','dwell_sec':235}, None). Ошибка → (None, msg).
    Пустая строка/комментарий → (None, None)."""
    s = (line or "").split("#", 1)[0].strip()
    if not s:
        return None, None
    m = _LABEL_RE.search(s)
    if not m:
        return None, f"нет метки этапа (формат X-Y-Z): {line.strip()!r}"
    label = f"{int(m.group(1))}-{int(m.group(2))}-{int(m.group(3))}"
    if stagenav.parse_label(label) is None:
        return None, f"метка вне диапазона (сложность 1-4, акт 1-3, этап 1-10): {label!r}"
    tm = re.search(r"(\d+)", s[m.end():])
    if not tm:
        return None, f"нет времени (сек) для {label}: {line.strip()!r}"
    dwell = int(tm.group(1))
    if dwell <= 0:
        return None, f"время должно быть >0 сек: {line.strip()!r}"
    return {"label": label, "dwell_sec": dwell}, None


def parse_route(text):
    """Многострочный текст → (stops, errors). stops = [{'label','dwell_sec'}]."""
    stops, errors = [], []
    for ln in (text or "").splitlines():
        stop, err = parse_line(ln)
        if err:
            errors.append(err)
        elif stop:
            stops.append(stop)
    return stops, errors


def parse_route_cfg(route):
    """Маршрут из config: строка ИЛИ список (строк / dict {label,dwell_sec|time}). → (stops, errors)."""
    if isinstance(route, str):
        return parse_route(route)
    stops, errors = [], []
    for item in (route or []):
        if isinstance(item, str):
            stop, err = parse_line(item)
            if err:
                errors.append(err)
            elif stop:
                stops.append(stop)
        elif isinstance(item, dict):
            lab = str(item.get("label", "")).strip()
            if stagenav.parse_label(lab) is None:
                errors.append(f"метка вне диапазона: {lab!r}")
                continue
            try:
                dwell = int(item.get("dwell_sec") or item.get("time") or 0)
            except (TypeError, ValueError):
                dwell = 0
            # без секунд (визуальный конструктор) → безопасный дефолт-таймер; защита от misclick
            # остаётся (CLEARED-гейт не даёт прыгнуть в момент боссового сундука).
            stops.append({"label": lab, "dwell_sec": dwell if dwell > 0 else 240})
    return stops, errors


def format_route(stops):
    """stops → редактируемый текст (для панели/файла)."""
    return "\n".join(f"{s['label']} / time: {int(s['dwell_sec'])} sec" for s in stops)


def suggest_route(hero_level, difficulty=None, n=4, dwell_sec=240, max_ahead=8):
    """Готовый маршрут «по стратегии»: hopper.plan_hops (разные уровни → свежие КД) с единым
    временем на этап. Это и есть залитый пресет — юзер потом правит время построчно."""
    import hopper
    stages = hopper.load_nav()
    pool = hopper.level_window(stages, hero_level, max_ahead=max_ahead)
    if difficulty:
        pool = hopper.cluster(pool, difficulty=difficulty)
    seq = hopper.plan_hops(pool, n)
    return [{"label": s["label"], "dwell_sec": int(dwell_sec)} for s in seq if s]


class RouteHop:
    """Таймерный обход маршрута. Дак-тайп под farm2._hop_step: on_log_events(events) + tick(now).

    navigate(stage_dict)->bool — колбэк перехода (stagenav.navigate). Провал навигации → остаёмся,
    повтор на следующем тике (лучше не прыгнуть, чем misclick)."""

    def __init__(self, stops, navigate, log=lambda *_: None, now=None, chest_grace_s=8.0):
        self.stops = list(stops)
        self.navigate = navigate
        self.log = log
        self._now = now or _time.time
        self.idx = -1                 # ещё не зашли на первый этап
        self.dwell_start = None
        self.hops = 0
        self.tracker = runtracker.HopController(chest_grace_s=chest_grace_s, now=now)

    def on_log_events(self, events):
        """Кормим runtracker (для защиты «не прыгать в момент боссового сундука»)."""
        for e in events:
            etype = e[0]
            kind = e[1] if len(e) > 1 else None
            ts = e[2] if len(e) > 2 else None
            self.tracker.on_event(etype, kind=kind, ts=ts)

    def _enter(self, idx, now):
        stop = self.stops[idx]
        if self.navigate({"label": stop["label"]}):
            self.idx = idx
            self.dwell_start = now
            self.tracker.set_stage(stop["label"])
            self.log(f"маршрут → {stop['label']} (стоять {stop['dwell_sec']}с)")
            return stop["label"]
        self.log(f"маршрут: навигация к {stop['label']} не удалась — повтор позже")
        return None

    def tick(self, now=None):
        """Если время на текущем этапе вышло (и не идёт боссовый сундук) — прыгнуть на следующий
        (по кругу). Возвращает label, на который прыгнули, иначе None."""
        if not self.stops:
            return None
        now = now if now is not None else self._now()
        if self.idx < 0:                                  # первый заход — идём на этап 1 маршрута
            return self._enter(0, now)
        if self.dwell_start is None:
            self.dwell_start = now
            return None
        if now - self.dwell_start < self.stops[self.idx]["dwell_sec"]:
            return None                                   # время на этапе ещё не вышло
        self.tracker.poll(now)
        if self.tracker.state == runtracker.CLEARED:      # босс убит, сундук не забран → ждём тик
            return None
        nxt = (self.idx + 1) % len(self.stops)
        lab = self._enter(nxt, now)
        if lab:
            self.hops += 1
        return lab


if __name__ == "__main__":
    demo = "3-3-9 / time: 235 sec\n# circuit\n2-1-4: 180\n4-2-7   300s"
    stops, errs = parse_route(demo)
    for s in stops:
        print(f"  {s['label']:8} {s['dwell_sec']}s")
    for e in errs:
        print("  ERR:", e)
    print("preset L65 NIGHTMARE:", format_route(suggest_route(65, "NIGHTMARE", n=3)).replace("\n", " | "))
