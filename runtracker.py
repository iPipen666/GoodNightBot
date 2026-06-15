"""runtracker.py — стейт-машина «прохода стадии» для безопасного тайминга хопа. WIP, лог-driven.

ПРОБЛЕМА (Денис): если телепортнуться сразу как убили босса — потеряем боссовый сундук (он падает
в конце прохода). Нельзя хопать пока: (1) босс не убит, (2) сундук не забран, (3) не начался НОВЫЙ
проход. Только тогда телепорт безопасен. Плюс: если пак не вывозит стадию (повторные вайпы) —
откатиться на N уровней ниже.

Источник событий — игровой лог RECORDS (logwatch/log_templates): stage_clear / getbox(+kind) /
defeat|stage_fail. Чистая логика без игры/сети → тестируется офлайн (test_runtracker.py).

Состояния прохода:
  IN_RUN   — идёт бой/волны (хоп ЗАПРЕЩЁН).
  CLEARED  — пришёл stage_clear (босс убит); ждём сундук.
  SECURED  — сундук забран (getbox после клира) ИЛИ истёк chest_grace (авто-открытие, патч 15.06).
  READY_HOP— после SECURED выждали new_run_settle (новый проход уже идёт) → телепорт БЕЗОПАСЕН.
"""
import time as _time

IN_RUN, CLEARED, SECURED, READY_HOP = "in_run", "cleared", "secured", "ready_hop"


class HopController:
    def __init__(self, pullback_levels=5, fail_threshold=3,
                 chest_grace_s=8.0, new_run_settle_s=3.0, now=None):
        self.state = IN_RUN
        self.stage = None                      # текущая стадия (label, напр. '4-2-7')
        self.level = None                      # её уровень (для pullback)
        self.t_clear = 0.0
        self.t_secured = 0.0
        self.fail_threshold = int(fail_threshold)
        self.pullback_levels = int(pullback_levels)
        self.chest_grace_s = float(chest_grace_s)
        self.new_run_settle_s = float(new_run_settle_s)
        self._fails = {}                       # stage_label -> подряд вайпов
        self._now = now or _time.time

    # ── вход: лог-событие ────────────────────────────────────────────────────
    def set_stage(self, label, level=None):
        """Зафиксировать, на какой стадии бот сейчас (после навигации). Сбрасывает проход в IN_RUN."""
        self.stage, self.level = label, level
        self.state = IN_RUN
        self.t_clear = self.t_secured = 0.0

    def on_event(self, etype, kind=None, ts=None):
        """Скормить лог-событие. Возвращает действие: None | 'pullback'.
        ('hop' решается через poll/ready_to_hop — он зависит от времени.)"""
        ts = ts if ts is not None else self._now()
        if etype == "stage_clear":
            if self.state == IN_RUN:           # босс убит — начинаем ждать сундук
                self.state = CLEARED
                self.t_clear = ts
                self._fails[self.stage] = 0    # прошли стадию → счётчик вайпов сброшен
        elif etype in ("getbox", "chest"):
            if self.state == CLEARED:          # сундук после клира → забран
                self.state = SECURED
                self.t_secured = ts
        elif etype in ("defeat", "stage_fail"):
            self._fails[self.stage] = self._fails.get(self.stage, 0) + 1
            if self._fails[self.stage] >= self.fail_threshold:
                return "pullback"              # пак не вывозит → откат на N уровней
        return None

    # ── время-зависимые переходы ─────────────────────────────────────────────
    def poll(self, now=None):
        """Догнать переходы по таймаутам (авто-открытие сундука, старт нового прохода)."""
        now = now if now is not None else self._now()
        if self.state == CLEARED and self.t_clear and now - self.t_clear >= self.chest_grace_s:
            self.state = SECURED               # сундук не залогался, но авто-открылся (грейс истёк)
            self.t_secured = self.t_clear + self.chest_grace_s   # реальный момент, чтобы каскад settle прошёл за 1 poll
        if self.state == SECURED and self.t_secured and now - self.t_secured >= self.new_run_settle_s:
            self.state = READY_HOP             # новый проход пошёл → телепорт безопасен

    def ready_to_hop(self, now=None):
        """Безопасно ли телепортиться ПРЯМО СЕЙЧАС (босс убит + сундук забран + новый проход идёт)."""
        self.poll(now)
        return self.state == READY_HOP

    def fails_on(self, label=None):
        return self._fails.get(label or self.stage, 0)

    def pullback_target_level(self):
        """Уровень, на который откатываться при провале (текущий − N, не ниже 1)."""
        base = self.level if self.level is not None else 1
        return max(1, base - self.pullback_levels)
