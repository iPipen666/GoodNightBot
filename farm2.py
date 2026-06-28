"""TBH — count-first главный цикл (farm2).

Loop: dismiss_popups → state.assess → действие.
Все существующие фиксы переиспользуются из farm.py (импортом, а не копией).
"""
import sys
import re
import random
import time

import numpy as np
import mss

import farm
import state
import items
import policy
import logx
import human
import idle
import inv_probe

# Минимум строк РАЗВЁРНУТОГО лога, при котором фоновый наблюдатель СЧИТАЕТ события. Ниже (1-строчная
# пилюля / кривой разворот / перекрытие панелью) — нестабильно, OCR-шум ломает сдвиг-счёт → перещёт.
# Юзер: «сканить логи только в развёрнутом на максимум состоянии при свёрнутом интерфейсе».
COUNT_MIN_LINES = int(farm.CFG.get("cycles", {}).get("count_min_lines", 4))


def _do_merge(sct, ctx):
    """Мерж: pre-lock ценного через items/policy, затем farm.merge_all."""
    if farm._hardstop():
        return 0
    # PRELOCK отключён по умолчанию (policy.prelock_enabled=false): требует рабочего OCR-чтения
    # тултипов (пока тултип не всплывает при программном наведении). Без pre-lock безопасность
    # держится грейд-гейтом farm.merge_all (forbid red=Бессмертный / epic) + разделением типов
    # autofill (бижу не смешивается со шмотом). Включить, когда OCR-наведение заработает.
    PRELOCK = farm.CFG.get("policy", {}).get("prelock_enabled", False)
    # 1) Pre-lock rare+ предметов перед слепым autofill
    try:
        hero = farm.ensure_open(sct, "hero") if PRELOCK else None
        if hero:
            # Alt+клик работает как lock только при ЗАКРЫТОМ кубе
            _, d = farm.detect(sct)
            if "cube" not in d and PRELOCK:
                cells = farm.grid_centers(
                    hero, "hero", "inv_tl", "inv_br",
                    farm.INV["cols"], farm.INV["rows"]
                )
                # размер ячейки для кропа (как в inv_probe)
                if len(cells) >= 2:
                    xs = sorted(set(c[2] for c in cells))
                    ys = sorted(set(c[3] for c in cells))
                    dx = (xs[-1] - xs[0]) / max(len(xs) - 1, 1) if len(xs) > 1 else 0
                    dy = (ys[-1] - ys[0]) / max(len(ys) - 1, 1) if len(ys) > 1 else 0
                else:
                    dx = dy = 0
                cw = max(int(dx * 0.95), 20)
                ch = max(int(dy * 0.95), 20)
                for r, c, x, y in cells:
                    img = np.array(sct.grab({
                        "left": int(x - cw / 2),
                        "top": int(y - ch / 2),
                        "width": cw,
                        "height": ch,
                    }))[:, :, :3]
                    a = inv_probe.analyze(img)
                    if a["rank"] in {"rare", "epic", "legendary", "red"}:
                        item = items.read_item(sct, (x, y))
                        decision = policy.decide(item, farm.CFG.get("policy", {}))
                        if decision == policy.LOCK:
                            human.click(x, y, farm.CFG, button="left", mod="alt")
                            logx.log_human(
                                f"залочил {item.get('name', '?')} ({a['rank']})"
                            )
    except Exception as e:
        logx.log_human(f"[pre-lock] ошибка: {e!r}")

    # 2) Сам мерж — полностью переиспользуем farm.merge_all
    m = farm.merge_all(sct)
    logx.log_human(f"смержил наборов: {m}")
    farm._stat(merges=farm.STATS.get("merges", 0) + m)
    # feedback-гейт: пустой мерж -> кулдаун (нечего мержить, не долбить куб каждый цикл)
    if m == 0:
        ctx["merge_cooldown"] = farm.CFG.get("state", {}).get("merge_dry_cooldown", 6)
    else:
        ctx["merge_cooldown"] = 0
    return m


def _do_save(sct, ctx):
    """Раскладка в стэш: сначала снять попап, потом do_saveall_sort."""
    if farm._hardstop():
        return
    farm.dismiss_popups(sct)
    farm.do_saveall_sort(sct)
    ctx["cycles_since_save"] = 0


def _do_chest(ctx):
    """Открыть сундуки."""
    if farm._hardstop():
        return
    farm.do_chests()
    ctx["cycles_since_chest"] = 0


def _do_mail(sct, ctx):
    """Проверка почты (туда падают итемы/сундуки, особенно после попапа «удалено с
    сервера»): открыть -> ждать ~10с -> ОБНОВИТЬ -> получить все -> закрыть.
    ПОРЯДОК критичен: refresh ВСЕГДА до «получить все» (иначе теряем почту).
    Кнопки привязаны к СОБСТВЕННОМУ баннеру MAIL BOX
    (vision detect 'mail'). Детект гейтит клики: НЕТ баннера -> НЕ кликаем (иначе
    попадём в нав-бар HERO и откроем куб). hero-иконка open_mail открывает почту."""
    if farm._hardstop():
        return
    ctx["last_mail_ts"] = time.time()  # ставим сразу — при сбое не долбить
    hero = farm.ensure_open(sct, "hero")
    if not hero:
        logx.log_human("[почта] HERO не открылся — пропуск"); return
    inv_before = farm.inv_fill(sct)
    farm.click_mail_icon(sct)               # template-матч иконки конверта (надёжно) + fallback offset
    mail = None
    for _ in range(10):                      # поллинг детекта MAIL BOX ~3с
        if not farm.isleep(0.3):
            return                            # СТОП — мгновенно выходим
        mail = farm.detect(sct)[1].get("mail")
        if mail:
            break
    if not mail:
        logx.log_human("[почта] не открылась — пропуск (без слепых кликов)")
        human.key("esc", farm.CFG); return
    logx.log_human("[почта] открыл")
    # ПОРЯДОК ЖЁСТКИЙ (требование юзера): ждать -> ОБНОВИТЬ -> получить все.
    # НЕЛЬЗЯ жать «получить все» до обновления — иначе риск потерять почту
    # (refresh подгружает то, что упало/«удалено с сервера»; забор до него теряет это).
    # 1) ждать таймер кнопки «Обновить» (~10с)
    wait_s = int(farm.CFG.get("state", {}).get("mail_refresh_wait", 10))
    logx.log_human(f"[почта] жду {wait_s}с до обновления…")
    if not farm.isleep(wait_s):
        return
    # 2) ОБНОВИТЬ первым (таймер прошёл -> кнопка активна)
    mail = farm.detect(sct)[1].get("mail") or mail
    farm.click_el(mail, "mail", "mail_refresh", "обновить", fast=True)
    if not farm.isleep(1.5):
        return
    # 3) ТЕПЕРЬ получить все
    mail = farm.detect(sct)[1].get("mail") or mail
    farm.click_el(mail, "mail", "mail_get_all", "получить все", fast=True)
    if not farm.isleep(0.9):
        return
    human.key("esc", farm.CFG)
    if not farm.isleep(0.5):
        return
    # честный итог: открыть hero (иначе инвентарь не читается) и сравнить до/после —
    # mail-итемы падают в инвентарь
    farm.ensure_open(sct, "hero")
    inv_after = farm.inv_fill(sct)
    if inv_before >= 0 and inv_after > inv_before:
        logx.log_human(f"[почта] забрал предметов: {inv_after - inv_before}")
    else:
        # боксы/камни-саммоны падают НЕ в обычный инвентарь -> дельта их не видит;
        # «получить все» отработал, но точный учёт неясен -> нейтрально, без вранья
        logx.log_human("[почта] проверена (получить все нажато)")


def _fmt_grades(g):
    """Разбивка {грейд: n} → строка, сорт от низшего тира к высшему, 'неизв' в конец."""
    order = {ru: t for t, ru in enumerate(items.RANK_TIERS)}
    return ", ".join(f"{n} {gr}" for gr, n in
                     sorted(g.items(), key=lambda kv: order.get(kv[0], 99)))


def prescan(sct, detailed=None):
    """Осмотр в ДВЕ ФАЗЫ (как просил юзер):
    ФАЗА 1 — БЫСТРО: открыть инвентарь и каждую вкладку тайника, СОСЧИТАТЬ занятость (по яркости,
             БЕЗ наведения/OCR — мгновенно). Сразу видно сколько и где лежит.
    ФАЗА 2 — последовательно прочитать КАЖДЫЙ предмет (OCR тултипа, грейд из словаря 10 грейдов),
             пропуская заведомо ПУСТЫЕ вкладки (из фазы 1) — не тратим OCR впустую."""
    use_ocr = detailed if detailed is not None else farm.CFG.get("policy", {}).get("prescan_ocr", True)
    if farm._hardstop():
        return

    # ── ФАЗА 1: быстрый подсчёт занятости ──
    logx.log_human("СКАН 1/2: считаю занятость (быстро)")
    hero = farm.ensure_inventory_tab(sct) or farm.ensure_open(sct, "hero")
    if farm._hardstop():
        return
    inv_n = 0
    if hero:
        inv_n, _ = farm.count_filled(sct, hero, "hero", "inv_tl", "inv_br",
                                     farm.INV["cols"], farm.HERO_ROWS)
    logx.log_human(f"инвентарь: {inv_n} занято")
    rc = farm.remember_landing_slot(sct, hero)        # куда упадёт новый лут (первая пустая ячейка)
    if rc is not None:
        logx.log_human(f"посадочная ячейка лута: ряд {rc[0]+1} кол {rc[1]+1} — буду чекать точечно")
    elif inv_n:
        logx.log_human("инвентарь полон — новый лут пойдёт в почту")
    if farm._hardstop():
        return
    st = None
    tab_counts = {}
    # СТАРТ-СКОРОСТЬ: обход всех вкладок тайника на старте — самый долгий шаг (открыть тайник +
    # 6 кликов + счёт). Если policy.prescan_stash=false — пропускаем, фарм стартует сразу; тайник
    # досканится в обычных save/sort-циклах. Включить обратно — флаг в true.
    if farm.CFG.get("policy", {}).get("prescan_stash", True):
        st = farm.ensure_open(sct, "stash")
        if not st:
            logx.log_human("тайник не открылся — пропуск")
        else:
            for tab in range(1, farm.STASH_TABS + 1):
                if farm._hardstop():
                    return
                farm.click_el(st, "stash", f"tab{tab}", f"вкладка {tab}", fast=True)
                farm.isleep(farm.COUNT_SETTLE)
                n, _ = farm.count_filled(sct, st, "stash", "grid_tl", "grid_br", 7, 6, park=False)
                tab_counts[tab] = n
                logx.log_human(f"тайник вкл{tab}: {n} занято")
    else:
        logx.log_human("тайник: скан отложен (быстрый старт) — досканю в циклах")
    total = inv_n + sum(tab_counts.values())
    if use_ocr:
        logx.log_human(f"ИТОГО занято: {total} — читаю детально 2/2…")
    if not use_ocr or farm._hardstop():
        if not farm._hardstop():
            logx.log_human("СКАН готов 🌙")
        return
    if not farm.ensure_game_foreground(force=True):
        logx.log_human("детальный скан пропущен: окно игры не впереди"); return

    # ── ФАЗА 2: последовательный OCR каждого предмета (пустые вкладки пропускаем) ──
    if farm._hardstop():
        return
    hero = farm.ensure_inventory_tab(sct) or hero
    if hero and inv_n:
        g = farm.scan_inv_full(sct, hero, ocr=True, flip="left")
        logx.log_human(f"инвентарь: {sum(g.values())} — " + (_fmt_grades(g) or "?"))
    if st:
        for tab in range(1, farm.STASH_TABS + 1):
            if farm._hardstop():
                return
            if tab_counts.get(tab, 0) == 0:
                continue                                   # пустая вкладка — не тратим OCR
            farm.click_el(st, "stash", f"tab{tab}", f"вкладка {tab}")
            farm.isleep(0.3)
            st = farm.detect(sct)[1].get("stash", st)
            g = farm.scan_grades(sct, st, "stash", "grid_tl", "grid_br", 7, 6,
                                 ocr=True, flip="right")
            logx.log_human(f"тайник вкл{tab}: {sum(g.values())} — " + (_fmt_grades(g) or "?"))
    logx.log_human("СКАН готов 🌙")


def _log_scan_valuable():
    """СЛИВ новых дропов, которые насчитал Observer (_observe_log) — для лог-прелока и интела.
    САМ лог НЕ опрашивает: единственный источник observe() — состояние наблюдения (без гонок за
    _prev_lines). True если в логе мелькнул ценный дроп (бижу) → форс инвентарь-скана. Грейд из
    лог-строки не виден → бижу ловим по имени, Immortal+ дочитываем по слоту в _drop_feed."""
    pol = farm.CFG.get("policy", {})
    if not pol.get("log_prelock", True) or farm._LOG is None:
        return False
    try:
        hit = False
        for nm in farm._LOG.drain_new_items():
            rec = items.classify(nm)
            if rec and rec.get("accessory"):
                logx.log_human(f"🛡 лог: ценный дроп «{nm}» → проверяю инвентарь")
                hit = True
        # ЛУТ-ИНТЕЛ: дропы с дочитанным мобом-источником (имя ← моб [время]) — сохраняем ВСЕ в
        # журнал, в живой лог выводим только ценное (бижу), чтобы не спамить обычным лутом.
        for r in farm._LOG.drain_new_intel():
            nm, mob, ts = r.get("name"), r.get("mob"), r.get("ts")
            if not (nm and mob):
                continue
            tag = f" [{ts}]" if ts else ""
            try:
                import sessionlog
                sessionlog.record("loot", f"«{nm}» ← {mob}{tag}")
            except Exception:
                pass
            rec = items.classify(nm)
            if rec and rec.get("accessory"):
                logx.log_human(f"🔹 ценный «{nm}» с «{mob}»{tag}")
        return hit
    except Exception as e:
        logx.log_human(f"[логвотч] {e!r}")
        return False


def _audit_chests(new, total, n, rows):
    """АУДИТ точности счёта: каждый ЗАСЧИТАННЫЙ сундук → строка в chest_audit.log + СНИМОК видимых
    строк лога в этот момент. Цель — замером (не на словах) убедиться, что нет дублей: если одна и
    та же лог-строка сундука засчитана в двух соседних снимках → перещёт виден глазами/grep'ом.
    Дёшево (append-only), не ломает фарм. Источник истины для вопроса «уверен в счётчике?»."""
    chests = [e for e in new if e.get("type") == "chest"]
    if not chests:
        return
    try:
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chest_audit.log")
        ts = time.strftime("%H:%M:%S")
        with open(p, "a", encoding="utf-8") as f:
            for e in chests:
                f.write(f"{ts} COUNT total={total} n_lines={n} kind={e.get('kind')} "
                        f"mob={e.get('mob','')!r} key={e.get('k')!r}\n")
            f.write(f"   snapshot[{n}]: " + "  ||  ".join(rows) + "\n")
    except Exception:
        pass


def _recolor_chest_kinds(new, rows_full, frame, lw):
    """Поправить тип ЗАСЧИТАННЫХ сундуков по ЦВЕТУ строки (надёжнее обрезаемого текста): СИНИЙ→
    stage_boss, КРАСНЫЙ→act_boss, СЕРЫЙ→normal. Двигаем счётчики lw.chests, чтобы корзины были верны
    (живьём boss-сундук с обрезанным «этапа» падал в normal → stage_boss=0). Цвет неуверен → не трогаем
    (остаётся текст-классификация). Сопоставляем событие↔строку по тексту из ключа (nots-сундуки)."""
    if frame is None or not new:
        return
    # ⚠️ ЦВЕТ ПО УМОЛЧАНИЮ ВЫКЛ (policy.chest_color_kind=false): на ПРОЗРАЧНОМ оверлее
    # полупрозрачная пилюля пропускает ФОН (синяя страница SHANN) → цвет загрязнён в ОБЕ стороны
    # (ложно-синий на обычных; серые блики на boss). Замерено живьём. Текст-фикс (chest_kind_for,
    # префикс маркера при обрезке «этапа»→«эта») НАДЁЖНЕЕ и не зависит от фона. Цвет — опционально
    # для ЧИСТОГО фона за игрой. НИКОГДА не перебиваем boss→normal (только добавляем boss-детект).
    if not farm.CFG.get("policy", {}).get("chest_color_kind", False):
        return
    import logwatch
    try:
        arr = np.asarray(frame)[:, :, :3].astype("int16")
    except Exception:
        return

    def nrm(s):
        return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower()).strip()

    boxes = {}
    for t, b in rows_full:
        boxes.setdefault(nrm(t), b)
    for e in new:
        if e.get("type") != "chest":
            continue
        parts = (e.get("k", "") or "").split("|", 3)
        line = parts[3] if len(parts) >= 4 else ""      # nots|chest|kind|<строка>
        b = boxes.get(nrm(line))
        if not b:
            continue
        ck = logwatch.chest_kind_by_color(arr, b)
        # ТОЛЬКО добавляем boss-детект (normal→stage_boss/act_boss), НИКОГДА не перебиваем boss→normal
        # (серые блики текста ложно дают normal). Текст-фикс уже ловит обрезанный boss — цвет лишь усиливает.
        if ck in ("stage_boss", "act_boss") and e.get("kind") == "normal":
            lw.chests["normal"] = max(0, lw.chests.get("normal", 0) - 1)
            lw.chests[ck] = lw.chests.get(ck, 0) + 1
            e["kind"] = ck


def _log_observer_loop(stop_event):
    """ФОНОВЫЙ непрерывный наблюдатель лога (~1.5с). Раньше счёт был ТОЛЬКО в idle-ветке прохода →
    пропускал ПАЧКИ сундуков, прилетающие во время прохода (подтверждено живьём: standalive-observe
    считал 6 сундуков, бот 0). Теперь поток читает лог НЕПРЕРЫВНО (find_log → observe), считает события
    и кормит дашборд. Единственный писатель в farm._LOG (observe под локом) → без гонок."""
    import log_setup
    while not (stop_event is not None and stop_event.is_set()):
        try:
            if farm._LOG is not None:
                # БЕЗ foreground-gate: игра — always-on-top оверлей, пилюли лога грабятся всегда
                # (фокус нужен только для КЛИКОВ, не для чтения). Просвет отсекает _is_log_line.
                r = log_setup.find_log()
                n = r.get("n", 0)
                # 🔴 ПЕРЕЩЁТ-ФИКС (юзер): СЧИТАЕМ ТОЛЬКО на РАЗВЁРНУТОМ многострочном логе (n>=COUNT_MIN)
                # при ЗАКРЫТОМ интерфейсе. В нестабильных состояниях (1-строчная пилюля n=1, кривой
                # разворот «строк 2», переходы при открытых HERO/стэше — лог мерцает/перекрыт) OCR шумит
                # → сдвиг-алайнмент недооценивает перекрытие → ПЕРЕСЧИТЫВАЕТ строки (вот откуда 211 за ночь).
                # При открытых панелях рамка RECORDS не видна → n мал → скип (юзер: «HERO открыт — рамки нет»).
                # Базлайн НЕ трогаем при скипе → события за время перекрытия досчитаются при ВОЗВРАТЕ в
                # развёрнутый вид (ограничено размером окна = без раздувания).
                if n >= COUNT_MIN_LINES:
                    rows_full = r.get("rows", [])
                    rows = [t for t, _b in rows_full]
                    new = farm._LOG.observe(rows)
                    if new:
                        # ТИП СУНДУКА ПО ЦВЕТУ (юзер: серый=обычный, синий=этапа, красный=акта) —
                        # надёжнее обрезаемого маркизой текста. Правит корзины ДО лога/аудита.
                        _recolor_chest_kinds(new, rows_full, r.get("frame"), farm._LOG)
                        nb = sum(1 for e in new if e["type"] == "chest")
                        if nb:
                            logx.log_human(f"📜 +{nb} сунд. (лог) — всего {farm._LOG.chests_total}")
                            _audit_chests(new, farm._LOG.chests_total, n, rows)
                lw = farm._LOG                            # дашборд обновляем ВСЕГДА (показать текущие тоталы)
                farm._stat(box_normal=lw.chests.get("normal", 0),
                           box_stage=lw.chests.get("stage_boss", 0),
                           box_act=lw.chests.get("act_boss", 0),
                           stages_ok=lw.stages_cleared, stages_fail=lw.stages_failed)
        except Exception:
            pass
        time.sleep(1.5)


def _observe_log(ctx):
    """Лёгкий ТРИГГЕР-проход (СЧЁТ лога теперь в фоновом потоке _log_observer_loop). Здесь только:
    реакция на дельту фонового счётчика (новый сундук в логе → открыть в этом проходе) + дешёвый
    визуальный триггер сундука по стоку."""
    if farm._LOG is None:
        return
    tot = farm._LOG.chests_total
    if tot > ctx.get("_obs_last_total", 0):          # фоновый счётчик вырос → новый сундук в логе
        ctx["_obs_last_total"] = tot
        ctx["last_scan_ts"] = 0                       # новый дроп → форс скана/прелока
        if "chest_pending_at" not in ctx:            # запланировать открытие через 2–5с (человечно,
            cc = farm.CFG.get("chest", {})           # НЕ сразу). Один Пробел. Только по лог-событию.
            lo = float(cc.get("open_delay_min", 2.0))
            hi = float(cc.get("open_delay_max", 5.0))
            ctx["chest_pending_at"] = time.time() + random.uniform(lo, hi)
            logx.log_human(f"📦 сундук в логе → открою через {ctx['chest_pending_at'] - time.time():.1f}с")


def _smart_pass(sct, ctx):
    """Умный полный проход (как просил юзер): панели → сундуки → попап → почта(таймер) →
    быстрый счёт → мерж всего мержабельного → раскладка остатков. Мерж получает ход КАЖДЫЙ
    проход (раньше его глушили save/chest-таймеры). Безопасность мержа (9/9, OCR-грейд,
    бижу/Бессмертный+ — лок) не меняется — внутри farm.merge_all."""
    if farm._hardstop():
        return
    farm._bot_cursor[0] = None
    farm.clear_panels(sct)                       # закрыть runes/status/… поверх куба/стэша
    # ЛОГ-СТАТУС (пассивно, без слепых кликов в Настройки): раз в ~30с проверяем по тексту, виден ли
    # лог, и обновляем индикатор. Если не виден — разово напоминаем юзеру закрепить (без misfire-кликов).
    try:
        import log_setup
        if time.time() - ctx.get("last_logcheck_ts", 0) > 12:
            ctx["last_logcheck_ts"] = time.time()
            n = log_setup.find_log().get("n", 0)
            if n != -1:                                         # -1 = игра не поверх → молчим, не проверка
                ready = n >= COUNT_MIN_LINES                    # СЧЁТ идёт ТОЛЬКО на развёрнутом логе (≥гейт)
                was = ctx.get("_log_ready")
                farm._stat(records_ready=ready)
                if ready and was is not True:                   # развернулся достаточно → счёт пошёл
                    logx.log_human(f"✓ лог развёрнут: {n} строк — счёт идёт")
                elif not ready and was is not False:
                    logx.log_human(f"лог свёрнут ({n} стр) — счёт ждёт разворота (нужно ≥{COUNT_MIN_LINES})")
                ctx["_log_ready"] = ready
    except Exception:
        pass
    _popup = farm.dismiss_popups(sct)             # template-матч Confirm (основной)
    if not _popup:                                # промахнулся → OCR-детект + клик Confirm по калибровке
        try:
            import records_ctl
            _popup = records_ctl.close_validation_popup(farm.CFG)
        except Exception:
            _popup = False
    if _popup:                                    # серверный попап «удалено с сервера» закрыт?
        ctx["mail_due_at"] = time.time() + 30     # -> «удалённые» предметы вернутся в почту ~30с
        logx.log_human("[попап] валидация снята → проверю почту через ~30с")
    # ЛОГ-СКАН: ценный дроп (бижу) в логе → форс инвентарь-прелока в этом же проходе
    if _log_scan_valuable():
        ctx["last_scan_ts"] = 0
    CY = farm.CFG.get("cycles", {})
    STT = farm.CFG.get("state", {})
    now = time.time()
    _observe_log(ctx)                             # КАЖДЫЙ проход: лог-событие сундука → план открытия
    # 1) сундуки — ТОЛЬКО по лог-событию (запланировано в _observe_log на +2–5с), ОДИН Пробел.
    #    Никаких таймеров/бёрстов: новый сундук в логе → ждём 2–5с → жмём Пробел один раз.
    pend = ctx.get("chest_pending_at")
    if pend is not None and now >= pend and not farm._hardstop():
        _do_chest(ctx)
        ctx["last_chest_ts"] = time.time()
        ctx.pop("chest_pending_at", None)
        if farm.dismiss_popups(sct):
            ctx["mail_due_at"] = time.time() + 30
            logx.log_human("[попап] валидация снята → проверю почту через ~30с")
    # 2) почта — по своему периоду ИЛИ форс после попапа валидации (туда падают итемы/боксы)
    mail_every = CY.get("mail_every_sec", 330)
    mail_due = time.time() >= ctx.get("mail_due_at", float("inf"))
    if not farm._hardstop() and STT.get("mail_enabled", True) \
            and (time.time() - ctx.get("last_mail_ts", 0) >= mail_every or mail_due):
        _do_mail(sct, ctx)
        ctx.pop("mail_due_at", None)
    # 3) скан инвентаря + мерж + раскладка — по своему периоду
    if not farm._hardstop() and time.time() - ctx.get("last_scan_ts", 0) >= CY.get("scan_every_sec", 15):
        _scan_merge_save(sct, ctx)
        ctx["last_scan_ts"] = time.time()
    # 4) АВТОРАЗВОРОТ лога (gated, дефолт OFF до живой верификации): закрыть панели → вернуться в
    # бой-вид → развернуть RECORDS до многострочного (стабильный счёт). Юзер: «после дел — закрыть HERO».
    # Достаточно ОДНОГО успеха (развёрнутое окно держится). matchTemplate ⛶ + safe thresholds (no blind click).
    if not farm._hardstop() and farm.CFG.get("policy", {}).get("records_autoexpand", False):
        try:
            farm.clear_panels(sct)                # вернуться в бой-вид (HERO/стэш закрыты → лог виден)
            import records_ctl
            records_ctl.pin_and_expand(farm.CFG, log=logx.log_human)
        except Exception as e:
            logx.log_human(f"[авторазворот] {e!r}")


def _lockworthy(name, grade, pol):
    """Ценен ли дроп для лока: бижутерия (любой грейд, по items.classify) ИЛИ грейд >= порога
    (Immortal+ по умолч.). Возвращает (bool, причина). Имя нераспознано → не лочим тут (мерж-гейт
    всё равно защитит грейдом)."""
    nm = (name or "").lower()
    for h in pol.get("hoard_names", []):          # список «никогда не синтезировать» — теперь живой
        if h and h.lower() in nm:
            return True, "хранимое"
    rec = items.classify(name) if name else None
    if rec and rec.get("accessory"):
        return True, "бижу"
    if grade:
        try:
            if items.rank_to_tier(grade) >= int(pol.get("lock_from_tier", 4)):
                return True, grade
        except Exception:
            pass
    return False, None


def _drop_feed(sct, hero, ctx):
    """Новые предметы в инвентаре → OCR имя/грейд (через farm._drop_line) → строка в лог
    «дроп: «Имя» ур.N · грейд» (в БД кликабельно). Бессмертный+ → празднование на таймере.
    Bounded: только ДЕЛЬТА занятых ячеек, максимум policy.ocr_drops_max чтений за раз."""
    pol = farm.CFG.get("policy", {})
    if not pol.get("ocr_drops", True):
        return
    if not human.is_foreground(farm.game_hwnd()):
        return                                  # без фокуса тултип не читается — пропуск
    cells = farm.grid_centers(hero, "hero", "inv_tl", "inv_br", farm.INV["cols"], farm.HERO_ROWS)
    s = farm.CFG.get("grid_cell_capture_size", 44)
    occ = {}
    for r, c, x, y in cells:
        img = np.array(sct.grab({"left": int(x - s / 2), "top": int(y - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) >= farm.SLOT_FILL_THR:
            occ[(r, c)] = (x, y)
    prev = ctx.get("_drop_snap")
    ctx["_drop_snap"] = set(occ.keys())
    if prev is None:
        return                                  # первый проход — только снимок, без спама
    new = [rc for rc in occ if rc not in prev]
    if not new or len(new) > 12:                # >12 = переснялось после раскладки — не спамим
        return
    # ЛОГ-ПРЕЛОК: лочим Alt-кликом только при ЗАКРЫТОМ кубе (иначе Alt-клик = положить В куб!)
    lock_on = pol.get("log_prelock", True)
    cube_open = False
    if lock_on:
        try:
            _, _d = farm.detect(sct)
            cube_open = "cube" in _d
        except Exception:
            cube_open = True                    # не уверены — НЕ лочим (без риска положить в куб)
    locked = ctx.setdefault("_locked", set())
    for rc in new[:int(pol.get("ocr_drops_max", 6))]:
        if farm._hardstop():
            break
        x, y = occ[rc]
        line = farm._drop_line(sct, x, y)
        if not line:
            continue
        logx.log_human("дроп: " + line)         # _pretty → общий(🔹)+лут, «Имя» кликабельно в БД
        nm = re.search(r"«([^»]+)»", line)
        name = nm.group(1) if nm else None
        m = re.search(r"·\s*(\S+)\s*$", line)
        grade = m.group(1) if m else None
        # защита ценного: бижу (любой грейд) / Immortal+ → лок ДО мержа (закрывает F11)
        if lock_on and not cube_open and rc not in locked:
            worth, why = _lockworthy(name, grade, pol)
            if worth:
                human.click(x, y, farm.CFG, button="left", mod="alt")
                locked.add(rc)
                logx.log_human(f"🔒 защита: залочил «{name or '?'}» ({why})")
        if grade and items.rank_to_tier(grade) >= 4:     # бессмертный+ → HELL YEAH
            rec = items.classify(name) if name else None
            t = (rec or {}).get("part_ru") or (rec or {}).get("type") or "RANK DROP"
            farm._stat(celebrate=str(t).upper())


def _scan_merge_save(sct, ctx):
    """РЕАКТИВНО: быстро посчитать инвентарь. Лезть в куб/стэш ТОЛЬКО если есть что разбирать
    (инвентарь дорос до порога мержа ИЛИ появился новый лут с прошлого раза — мобы роняют
    предметы прямо в инвентарь без сундука). Иначе — мгновенно дальше, не теряем скорость."""
    if farm._hardstop():
        return
    hero = farm.ensure_inventory_tab(sct)
    # ПОСАДОЧНАЯ ЯЧЕЙКА: устарела (после save/sort инвентарь сдвинулся) → пересчитать тут, HERO открыт.
    # Дёшево проверяем, прилетел ли лут именно в неё — точечный сигнал поверх общего счёта.
    landed = farm.landing_filled(sct, hero)        # True/False/None (None = надо пересчитать)
    if landed is None and hero:
        farm.remember_landing_slot(sct, hero)
    inv_n = farm.inv_fill(sct)
    prev = ctx.get("last_inv_fill", -1)
    ctx["last_inv_fill"] = inv_n
    if hero:
        _drop_feed(sct, hero, ctx)                # новые предметы → лог со ссылкой в БД + празднование
        # _tally_loot_stats УБРАН: считал стоящий в инвентаре лут (старьё) → плитки врали («материалы 2»
        # на давно лежащем). Дашборд теперь лог-driven (сундуки/этапы/синтез). Скан рамок per-cell тут
        # был и тормозом, и враньём — не зовём.
        if landed:                                # посадочная ячейка посветлела → новый предмет именно там
            farm.remember_landing_slot(sct, hero) # сдвинуть указатель на следующую пустую
    merge_min = farm.CFG.get("state", {}).get("merge_inv_min", 9)
    grew = (inv_n > prev >= 0) or bool(landed)     # новый лут: рост счёта ИЛИ посадочная заполнилась
    if inv_n < 0:
        return
    if inv_n < merge_min and not grew:
        return                                     # нечего разбирать — хуяк дальше
    # ⛔ КУБ/МЕРЖ ВЫКЛЮЧЕН по умолчанию (policy.merge_enabled=false): юзер НЕ хочет слепой автофилл;
    # ждём реворк (ручная раскладка 9). Но SAVE-ALL (перелив в тайник) БЕЗОПАСЕН (без куба) и
    # ОБЯЗАТЕЛЕН — иначе инвентарь за ночь забьётся и фарм встанет. Поэтому сейв идёт ВСЕГДА.
    if farm.CFG.get("policy", {}).get("merge_enabled", False):
        # АНТИ-ПЕТЛЯ: тот же объём инвентаря уже разбирали и мержить было нечего (остался только хлам
        # не из списка)? Не лезем в куб снова, пока не придёт НОВЫЙ лут (grew). Иначе бот каждый цикл
        # автофиллит те же отклонённые предметы и спамит лог — ровно то, на что жаловался юзер.
        if not grew and ctx.get("_merge_dry_fill") == inv_n:
            logx.log_human(f"инвентарь: {inv_n} занято — нового нет, перелив в тайник")
        else:
            logx.log_human(f"инвентарь: {inv_n} занято — разбираю кубом")
            merged_any = 0
            for _ in range(3):                    # мерж → пересчёт → повтор (cap 3, без зацикла)
                m = _do_merge(sct, ctx)
                merged_any += m or 0
                if not m or farm._hardstop():
                    break
                farm.ensure_inventory_tab(sct)    # куб вернул предмет → пересчитать, переоценить
                inv_n = farm.inv_fill(sct)
                ctx["last_inv_fill"] = inv_n
            ctx["_merge_dry_fill"] = inv_n if merged_any == 0 else None  # сухой объём → не долбить впустую
    else:
        logx.log_human(f"инвентарь: {inv_n} занято — перелив в тайник (куб выключен)")
    _do_save(sct, ctx)                            # ВСЕГДА: безопасный перелив в тайник, освобождает инвентарь


def _check_records_ready():
    """Старт-проверка лога RECORDS по ТЕКСТУ строк (log_setup.find_log) — надёжно, без слепых кликов
    в Настройки (на прозрачном оверлее доля-калибровка мажет → вред). Лог — фундамент счёта. Честно
    докладываем состояние; если плохо — просим юзера открыть/развернуть/закрепить (модалка позже)."""
    if getattr(farm, "_LOG", None) is None:
        return
    try:
        import log_setup
        n = log_setup.establish(farm.CFG, log=logx.log_human)   # НЕ блокирует, не закрывает хороший лог
        farm._stat(records_ready=(n >= COUNT_MIN_LINES))
        if n == -1:
            logx.log_human("лог не проверить — игра не поверх (ты активен). Дам экран — увижу сам")
        elif n >= COUNT_MIN_LINES:
            logx.log_human(f"✓ лог развёрнут: {n} строк — счёт идёт")
        elif n >= 1:
            logx.log_human(f"лог свёрнут ({n} стр) — разверну сам; счёт пойдёт от ≥{COUNT_MIN_LINES} строк")
        else:
            logx.log_human("лог RECORDS не виден — разверну/закреплю сам, как поймаю пилюлю")
    except Exception as e:
        logx.log_human(f"[лог-чек] {e!r}")


def ensure_log_ready(attempts=4, log=logx.log_human):
    """БЛОКИРУЮЩИЙ стартовый гейт лога RECORDS (Денис: «бот запустился → проверил окна → есть ли
    развёрнутый лог → нет? закрепил, навёлся, развернул до макс → начал работу»).

    КЛЮЧЕВОЙ ФИКС (найден живьём 2026-06-16): оценивать лог ТОЛЬКО ПОСЛЕ clear_panels — открытые
    HERO/STATUS/cube перекрывают лог, и find_log даёт ложный n=0 («закрыт»), хотя он открыт.
    Цикл: focus → clear_panels → find_log → если мало: открыть(Settings) + развернуть-до-макс
    (pin_and_expand растит строки клик-за-кликом пока растёт = подтверждённый максимум) → повтор.
    НЕ блокирует вечно: после attempts продолжаем (счёт догонит при развороте в цикле). (ready, n)."""
    import log_setup
    import records_ctl
    if not farm.focus_game():
        farm._stat(records_ready=False)
        log("лог-гейт: окно игры не найдено")
        return False, 0
    n = 0
    with mss.mss() as sct:
        for i in range(1, attempts + 1):
            if farm._hardstop():
                return False, n
            # КРИТИЧНО (Денис 2026-06-16): закрыть HERO/stash/cube — они перекрывают лог.
            # clear_panels НЕ закрывает HERO; collapse_for_observe ESC-ит пока hero/stash/cube видны.
            records_ctl.collapse_for_observe(farm.CFG, sct, log=log)
            records_ctl.reveal_log(farm.CFG, sct, log=log)   # КЛИК в поле лога → проявить RECORDS (ховер Unity не ловит)
            time.sleep(0.4)
            n = log_setup.find_log().get("n", 0)
            if n < COUNT_MIN_LINES:                         # реально закрыт → открыть через Settings
                log(f"лог-гейт {i}/{attempts}: n={n} < {COUNT_MIN_LINES} — открываю лог…")
                try:
                    records_ctl.ensure_ready(farm.CFG, log=log, expand=False)
                except Exception as e:
                    log(f"лог-гейт open err: {e!r}")
                time.sleep(0.3)
            try:
                records_ctl.pin_and_expand(farm.CFG, log=log)   # развернуть до МАКСИМУМА (рост строк)
            except Exception as e:
                log(f"лог-гейт expand err: {e!r}")
            n = log_setup.find_log().get("n", n)
            if n >= COUNT_MIN_LINES:
                farm._stat(records_ready=True)
                log(f"лог-гейт ✓ ({i}/{attempts}): развёрнут, n={n} — начинаю работу")
                return True, n
    farm._stat(records_ready=False)
    log(f"лог-гейт ⚠ не дошёл до готовности за {attempts} попыток (n={n}) — продолжу, досчитаю в цикле")
    return False, n


def _init_hop(ctx):
    """Собрать HopMode, если включён hop-режим (config.hop.enabled). БЕЗОПАСНО: без калибровки PORTAL
    stagenav.goto вернёт False → реальных прыжков не будет. Выкл → ctx['_hop']=None (нулевое влияние)."""
    h = farm.CFG.get("hop", {})
    ctx["_hop"] = None
    if not h.get("enabled"):
        return
    try:
        import stagenav
        # ОБЯЗАТЕЛЬНАЯ калибровка PORTAL под окно юзера — без неё хоп безопасно простаивает (кликов нет)
        cst, cdetail = stagenav.calibration_status()
        if cst != "ok":
            logx.log_human(f"⚠ ХОП ВКЛ, но PORTAL НЕ откалиброван ({cst}): {cdetail}. "
                           "Прыжков НЕ будет — прогони калибровку PORTAL в панели (вкладка Stage hop) "
                           "ИЛИ calibrate_portal.py. Фарм работает как обычно.")
        ctx["_hop_sc"] = ctx["_hop_ct"] = ctx["_hop_df"] = 0
        mode = (h.get("mode") or "strategy").lower()
        if mode == "route":                               # таймерный маршрут (кастомная карта)
            import routehop
            stops, errs = routehop.parse_route_cfg(h.get("route", []))
            for e in errs:
                logx.log_human(f"hop-маршрут: {e}")
            if not stops:
                logx.log_human("hop-маршрут пуст/невалиден — режим выключен")
                return
            ctx["_hop"] = routehop.RouteHop(stops, navigate=stagenav.navigate, log=logx.log_human)
            total = sum(s["dwell_sec"] for s in stops)
            logx.log_human(f"hop-режим МАРШРУТ ВКЛ: {len(stops)} этапов, круг ~{total}с "
                           "(stagenav кликает только при откалиброванном PORTAL)")
        else:                                             # пресет «по стратегии» (событийный juggling)
            import hopmode
            import hopper
            stages = hopper.load_nav()
            ctx["_hop"] = hopmode.HopMode(
                stages, hero_level=int(h.get("hero_level", 80)),
                navigate=stagenav.navigate, log=logx.log_human,
                difficulty=h.get("difficulty"), max_ahead=int(h.get("max_ahead", 8)))
            logx.log_human("hop-режим СТРАТЕГИЯ ВКЛ (stagenav кликает только при откалиброванном PORTAL)")
    except Exception as e:
        logx.log_human(f"hop-init err: {e!r}")


def _hop_step(ctx, now=None):
    """Скормить HopMode дельты лог-счётчиков (stage_clear/getbox/defeat) + тикнуть. No-op если hop off.
    Тайминг безопасен внутри HopMode/runtracker (не прыгаем пока босс не убит+сундук не забран)."""
    hm = ctx.get("_hop")
    if hm is None or getattr(farm, "_LOG", None) is None:
        return
    now = now if now is not None else time.time()
    lw = farm._LOG
    ev = []
    sc = getattr(lw, "stages_cleared", 0)
    if sc > ctx.get("_hop_sc", 0):
        ev += [("stage_clear", None, now)] * (sc - ctx["_hop_sc"]); ctx["_hop_sc"] = sc
    ct = sum((getattr(lw, "chests", {}) or {}).values())
    if ct > ctx.get("_hop_ct", 0):
        ev.append(("getbox", "stage_boss", now)); ctx["_hop_ct"] = ct
    df = getattr(lw, "defeats", 0)
    if df > ctx.get("_hop_df", 0):
        ev += [("defeat", None, now)] * (df - ctx["_hop_df"]); ctx["_hop_df"] = df
    if ev:
        hm.on_log_events(ev)
    hm.tick(now)


def _check_chest_autoopen():
    """Старт-детект сундукового HUD (chest_stock): авто-открытие ВКЛ/ВЫКЛ + сколько в стоке.
    ТОЛЬКО ДЕТЕКТ (без кликов). Юзер: «приоритетнее задетектить сундук, если ОТКЛЮЧЕНО автооткрытие».
    Не откалибровано → тихо подсказываем разово запустить калибратор; фарм работает и без этого."""
    try:
        import chest_stock
    except Exception:
        return
    try:
        if not chest_stock.chest_present():        # нет сундука в стоке → нечего проверять, мышь не двигаем
            farm._stat(chest_auto_open=None)
            return
        r = chest_stock.read(do_hover=True)       # бот сам наводится на сундук, будит «A», читает
        farm._stat(chest_auto_open=r.get("auto_open"))
        if r.get("no_fg") or r.get("no_game"):
            return                                # игра не поверх — молча, records-чек уже сказал
        if not r.get("calibrated"):
            logx.log_human("сундук-HUD не откалиброван — разок: python chest_stock.py (F8 над «A»)")
            return
        ao = r.get("auto_open")
        if ao is True:
            logx.log_human(f"авто-открытие сундуков ВКЛ (золотая «A», {r.get('gold')}px)")
            if farm.CFG.get("policy", {}).get("disable_chest_autoopen", False):
                res = chest_stock.toggle_off(log=logx.log_human)
                if res.get("ok"):
                    farm._stat(chest_auto_open=False)
                    logx.log_human("✓ авто-открытие выключено — открываю сундуки сам, контролируемо")
                else:
                    logx.log_human("«A» не потухла — открываю Пробелом всё равно (не критично)")
        elif ao is False:
            logx.log_human("авто-открытие сундуков ВЫКЛ — открываю Пробелом сам")
        else:
            logx.log_human("сундука в стоке нет — проверю позже")
    except Exception as e:
        logx.log_human(f"[сундук-чек] {e!r}")


def run(mode="live", log_cb=None, stat_cb=None, stop_event=None, politeness="polite") -> bool:
    """Главный count-first цикл.

    politeness:
      "polite" — ждать idle.idle_seconds() >= farm.IDLE_START перед каждым циклом,
                 длинные паузы между циклами (20–45 с).
      "auto"   — отсчёт 3-2-1 и старт, короткие паузы (8–20 с).
    """
    farm.set_hooks(log_cb, stat_cb, stop_event)
    try:
        import vision
        vision.reset_session_scale()       # окно/масштаб мог смениться между сессиями → переучить
    except Exception:
        pass
    farm.STATS.update(cycle=0, merges=0, box_normal=0, box_stage=0, box_act=0,
                      loot_valuable=0, loot_materials=0)   # счётчики — с нуля на каждую сессию
    if getattr(farm, "_LOG", None) is not None:
        farm._LOG.reset()                  # лог-счётчик сундуков — с чистого листа на сессию
    farm.LANDING.update(rc=None, empty_mean=None, stale=True)   # посадочная ячейка — сброс между сессиями (окно/масштаб мог смениться)
    if getattr(farm, "_LOG", None) is not None:                 # ФОНОВЫЙ наблюдатель лога: непрерывный счёт
        import threading                                        # (не пропускает пачки сундуков во время проходов)
        threading.Thread(target=_log_observer_loop, args=(stop_event,), daemon=True).start()
    # СИНХРОН politeness -> farm.POLITE: control.py зовёт без --rude в argv, поэтому
    # farm.POLITE по умолчанию True даже в "Сразу-авто" -> user_grabbed ложно прерывал
    # циклы (бот «уступал курсору», которого нет). auto = rude = не уступать.
    farm.POLITE = (politeness == "polite")
    parallel = (politeness == "parallel")   # клик по бою перед проходом + вернуть мышь юзеру
    DEBUG = "--debug" in sys.argv
    logx.setup(DEBUG, log_cb)

    if not farm.fw():
        logx.log_human("Окно игры не найдено")
        return False

    # Отсчёт для авто-режима
    if politeness == "auto":
        for i in (3, 2, 1):
            if farm._hardstop():
                logx.log_human("Отмена.")
                farm._stat(phase="стоп")
                return True
            farm._stat(phase=f"старт через {i}…")
            time.sleep(1)

    # СТАРТ: быстрый анализ ПЕРЕД фармом — счёт инвентаря + всех вкладок тайника (по яркости,
    # без потултипного OCR → быстро). Заодно прогревает детект панелей. Потом — реактивный цикл.
    if mode == "live" and not farm._hardstop() and farm.ensure_game_foreground(force=True):
        farm._stat(phase="скан")
        try:
            with mss.mss() as s0:
                farm.dismiss_popups(s0)
                farm.clear_panels(s0)         # ЗАКРЫТЬ руны/статус/настройки и пр. ДО прескана —
                                              # иначе они перекрывают HERO и прескан читает 0 (adverse-старт)
                prescan(s0, detailed=False)   # быстрый: только подсчёт, без OCR каждого предмета
        except Exception as e:
            logx.log_human(f"[скан] {e!r}")
        ensure_log_ready()                    # БЛОКИРУЮЩИЙ гейт: лог открыт+развёрнут до макс ДО фарма
        _check_chest_autoopen()               # сундуки: авто-открытие ВКЛ/ВЫКЛ? (детект, без кликов)
        logx.log_human("поехали 🚀")

    # СЧЁТ СОБЫТИЙ — через СОСТОЯНИЕ НАБЛЮДЕНИЯ (_observe_log) в idle-ветке цикла: единственный
    # источник observe() (сдвиг-счёт), без фонового потока → нет гонок за _prev_lines. Наблюдение
    # сворачивает панели + разворачивает лог + снимает ВЕСЬ лог + считает по сдвигу строк.

    ctx = {
        "cycle": 0,
        "last_inv_fill": -1,
        "merge_cooldown": 0,
        "last_mail_ts": 0.0,    # таймеры действий (0 = сработать в первый проход)
        "last_chest_ts": 0.0,
        "last_scan_ts": 0.0,
        "last_logopen_ts": 0.0,
    }
    _init_hop(ctx)                  # hop-режим (прыжки по стадиям) — если включён в config.hop.enabled

    once = mode in ("once", "dry")  # один проход и выход (тест/dry)
    while True:
        if farm._hardstop():
            try:
                logx.log_human(f"[ДИАГ-стоп] F12={human.kill_pressed(farm.KKEY)} stop_evt={farm._stopped()} cycle={ctx['cycle']}")
            except Exception:
                pass
            break

        # ВЕЖЛИВЫЙ старт-гейт (НЕ для once/dry)
        if politeness == "polite" and not once:
            while idle.idle_seconds() < farm.IDLE_START:
                if farm._hardstop():
                    break
                time.sleep(1.0)
            if farm._hardstop():
                break

        ctx["cycle"] += 1
        farm._stat(cycle=ctx["cycle"], phase="проход")

        # ВСЕГДА перед проходом: вывести игру вперёд РЕАЛЬНЫМ кликом по бою и проверить фокус —
        # без этого клавиши (Пробел=сундуки) и клики уходят мимо. parallel — ещё вернуть мышь юзеру.
        saved_cur = idle.cursor_pos() if parallel else None
        ok = farm.ensure_game_foreground(force=True)
        if not ok:
            logx.log_human("окно не найдено")
            if once or farm._hardstop():
                break
            time.sleep(1.0)
            continue

        with mss.mss() as sct:
            try:
                _smart_pass(sct, ctx)          # полный проход: сундуки → счёт → мерж → раскладка
            except Exception as e:
                logx.log_human(f"[проход] ошибка: {e!r}")
            human.loiter(sct, farm.CFG)

        if parallel and saved_cur:
            human.restore_cursor(saved_cur)    # вернуть мышь юзеру ровно на место
        else:
            human.park()

        if once or farm._hardstop():
            break

        # ждать до СЛЕДУЮЩЕГО ближайшего действия (сундуки/почта/скан) — для таймера-HUD
        c = farm.CFG.get("cycles", {})
        STT = farm.CFG.get("state", {})
        due = [(ctx["last_scan_ts"] + c.get("scan_every_sec", 15), "скан инвентаря")]
        if ctx.get("chest_pending_at"):                 # сундук запланирован по лог-событию
            due.append((ctx["chest_pending_at"], "сундук"))
        if STT.get("mail_enabled", True):
            due.append((ctx["last_mail_ts"] + c.get("mail_every_sec", 330), "почта"))
        next_ts, next_action = min(due, key=lambda t: t[0])
        iv = max(1.0, next_ts - time.time())
        if politeness == "polite":
            iv = max(iv, farm.IDLE_START)
        farm._stat(phase="ожидание", next_in=int(iv), next_action=next_action)
        slept = 0.0
        log_iv = float(farm.CFG.get("cycles", {}).get("log_every_sec", 2))
        obs_iv = float(farm.CFG.get("cycles", {}).get("observe_every_sec", 8))
        last_log = 0.0
        last_obs = 0.0
        while slept < iv:
            if farm._hardstop():
                break
            time.sleep(0.5)
            slept += 0.5
            # СОСТОЯНИЕ НАБЛЮДЕНИЯ: пока ждём — свернуть всё, развернуть лог, посчитать события по
            # сдвигу строк (новые сундуки/лут). Не в parallel (там мышь у юзера). Авторитет счёта.
            if not parallel and slept - last_obs >= obs_iv:
                last_obs = slept
                _observe_log(ctx)
                _hop_step(ctx)                        # hop-режим: дельты лог-счётчиков → тайминг прыжка (no-op если off)
            # МАКСИМАЛЬНО ЧАСТО читаем лог во время ожидания: ценный дроп (бижу) → прерываем
            # ожидание и сразу идём на проход → прелок успевает залочить до раскладки/мержа.
            if slept - last_log >= log_iv:
                last_log = slept
                if _log_scan_valuable():
                    ctx["last_scan_ts"] = 0
                    break

    farm._stat(phase="стоп")
    logx.log_human("Готово.")
    return True


def main():
    """CLI-точка входа."""
    if "--once" in sys.argv:
        mode = "once"
    elif "--live" in sys.argv:
        mode = "live"
    elif "--dry" in sys.argv:
        mode = "dry"
    else:
        mode = "live"

    politeness = "auto" if "--rude" in sys.argv else "polite"
    run(mode=mode, politeness=politeness)


if __name__ == "__main__":
    main()
