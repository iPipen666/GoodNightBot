"""hopmode.py — «мозг» режима прыжков по стадиям. WIP, тестируемый офлайн.

Связывает:
  • hopper    — ВЫБОР следующей стадии (рандом-перебор разных уровней; pullback на уровень ниже),
  • runtracker— ТАЙМИНГ (телепорт ТОЛЬКО когда босс убит + сундук забран + новый проход пошёл),
  • navigate  — колбэк перехода (stagenav.goto, подключится в задаче #3; пока стаб),
  • open_chest— колбэк открытия сундука (на случай ручного добора; авто-открытие игры это покрывает).

Использование (в farm2 hop-режиме):
  hm = HopMode(stages_nav, hero_level=88, navigate=stagenav.goto, log=...)
  # на каждый лог-проход:
  hm.on_log_events([("stage_clear",None,ts), ("getbox","stage_boss",ts2), ...])
  hm.tick(now)        # сам решит, пора ли прыгать, и прыгнет (если ready_to_hop)

Безопасность тайминга — в runtracker (не хопаем пока не забрали боссовый сундук). Здесь только
склейка выбора+навигации. Чистая логика, без игры → test_hopmode.
"""
import random

import hopper
import runtracker


class HopMode:
    def __init__(self, stages, hero_level, navigate, open_chest=None, log=lambda *_: None,
                 difficulty=None, max_ahead=8, seed=0, avoid_recent=3,
                 pullback_levels=5, fail_threshold=3, now=None):
        pool = hopper.level_window(stages, hero_level, max_ahead=max_ahead)
        if difficulty:                                   # держаться одной сложности → меньше навигации
            pool = hopper.cluster(pool, difficulty=difficulty)
        self.pool = pool or stages
        self.navigate = navigate                         # (stage_dict) -> bool (успех перехода)
        self.open_chest = open_chest
        self.log = log
        self.avoid_recent = avoid_recent
        self._rng = random.Random(seed)
        self._recent = []                                # последние уровни (для разнесения КД)
        self.hops = 0
        self.pullbacks = 0
        self.tracker = runtracker.HopController(
            pullback_levels=pullback_levels, fail_threshold=fail_threshold, now=now)

    def start_on(self, stage):
        """Зафиксировать стартовую стадию (после первой навигации/детекта)."""
        self.tracker.set_stage(stage.get("label"), stage.get("level"))
        self._note(stage)

    def _note(self, stage):
        self._recent.append(stage.get("level"))
        self._recent = self._recent[-self.avoid_recent:]

    def on_log_events(self, events):
        """events: список (etype, kind, ts). Кормит runtracker; обрабатывает pullback."""
        for e in events:
            etype = e[0]
            kind = e[1] if len(e) > 1 else None
            ts = e[2] if len(e) > 2 else None
            act = self.tracker.on_event(etype, kind=kind, ts=ts)
            if act == "pullback":
                self._do_pullback()

    def tick(self, now=None):
        """Если тайминг разрешает (босс убит+сундук забран+новый проход) — выбрать и прыгнуть.
        Возвращает label стадии, на которую прыгнули, или None."""
        if not self.tracker.ready_to_hop(now):
            return None
        nxt = hopper.next_stage(self.pool, self._recent, self._rng)
        if not nxt:
            return None
        if self.navigate(nxt):
            self.tracker.set_stage(nxt.get("label"), nxt.get("level"))
            self._note(nxt)
            self.hops += 1
            self.log(f"hop → {nxt.get('label')} (L{nxt.get('level')})")
            return nxt.get("label")
        self.log(f"hop: навигация к {nxt.get('label')} не удалась — остаюсь")
        return None

    def _do_pullback(self):
        """Пак не вывозит → выбрать стадию уровнем ≤ (текущий−N) и перейти."""
        target = self.tracker.pullback_target_level()
        lower = [s for s in self.pool if s.get("level", 10 ** 9) <= target]
        if lower:
            cand = max(lower, key=lambda s: s.get("level", 0))    # ближайшая снизу к цели
        elif self.pool:
            cand = min(self.pool, key=lambda s: s.get("level", 0))  # ниже цели нет → самая лёгкая в пуле
        else:
            cand = None
        if not cand:
            self.log("pullback: пул пуст — остаюсь")
            return
        if self.navigate(cand):
            self.tracker.set_stage(cand.get("label"), cand.get("level"))
            self._note(cand)
            self.pullbacks += 1
            self.log(f"pullback ↓ → {cand.get('label')} (L{cand.get('level')}, цель ≤{target})")
