r"""test_updates.py — юнит-тесты фич «обновляемый клиент + воронка в Telegram» (2026-06-15).

Покрывает:
  • config.json         — секции links.* и update.api присутствуют и валидны
  • i18n                 — новые ключи (tg_btn / upd_*) есть, t() резолвит en+ru, формат {v}/{e} работает
  • updater._api()       — берёт адрес из config.update.api, фолбэк на дефолт при отсутствии
  • updater._vtuple/_current — сравнение версий и чтение VERSION
  • control.py (статика) — проводка UI на месте (бейдж ✈, кнопка tg_btn, строка обновлений, методы)

Раннер как в проекте — НЕ pytest. Запуск:
  .\.venv\Scripts\python.exe test_updates.py     # exit 0 = всё ок, 1 = есть провал
"""
import os
import re
import json
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        _fails.append(name)


def ok(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fails.append(name)


# ── config.json ──
def test_config():
    print("config.json:")
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    links = cfg.get("links", {})
    ok("links.telegram is t.me url", str(links.get("telegram", "")).startswith("https://t.me/"))
    ok("links.telegram_bot is t.me url", str(links.get("telegram_bot", "")).startswith("https://t.me/"))
    upd = cfg.get("update", {})
    ok("update.api present & https", str(upd.get("api", "")).startswith("https://"))


# ── i18n ──
def test_i18n():
    print("i18n:")
    import i18n
    from i18n import t, LANG, LOCALES
    for key in ("tg_btn", "tg_opened", "upd_check", "upd_checking",
                "upd_latest", "upd_found", "upd_offline", "upd_err"):
        ok(f"key {key} in LANG", key in LANG)
        ok(f"key {key} has en-US", bool(LANG.get(key, {}).get("en-US")))
        ok(f"key {key} has ru-RU", bool(LANG.get(key, {}).get("ru-RU")))
    # резолв en + ru (не возвращает сам ключ)
    _orig = i18n._lang
    try:
        i18n._lang = lambda: "en-US"
        ok("tg_btn EN resolves", t("tg_btn") != "tg_btn" and "TELEGRAM" in t("tg_btn").upper())
        ok("upd_check EN resolves", t("upd_check") != "upd_check")
        # форматирование плейсхолдеров
        ok("upd_latest {v} formats", "1.2.3" in t("upd_latest", v="1.2.3"))
        ok("upd_found {v} formats", "1.2.3" in t("upd_found", v="1.2.3"))
        ok("upd_err {e} formats", "boom" in t("upd_err", e="boom"))
        i18n._lang = lambda: "ru-RU"
        ok("tg_btn RU resolves", t("tg_btn") != "tg_btn")
        # неизвестная локаль -> фолбэк на en (не ключ, не пусто)
        i18n._lang = lambda: "th-TH"
        ok("tg_btn TH falls back (not key)", t("tg_btn") not in ("", "tg_btn"))
    finally:
        i18n._lang = _orig


# ── updater ──
def test_updater():
    print("updater:")
    import updater
    # _api из config
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    want_api = (cfg.get("update", {}).get("api") or updater.API).rstrip("/")
    check("_api() from config", updater._api(), want_api)
    ok("_api() no trailing slash", not updater._api().endswith("/"))
    # сравнение версий
    ok("1.0.1 > 1.0.0", updater._vtuple("1.0.1") > updater._vtuple("1.0.0"))
    ok("1.2.0 > 1.1.9", updater._vtuple("1.2.0") > updater._vtuple("1.1.9"))
    ok("equal versions not greater", not (updater._vtuple("1.0.0") > updater._vtuple("1.0.0")))
    ok("garbage version safe", updater._vtuple("oops") == (0,))
    # _current читает VERSION
    ok("_current() returns dotted ver", re.match(r"^\d+(\.\d+)+$", updater._current()) is not None)
    # check() при недостижимом сервере -> None (не падает). Подменяем api на заведомо мёртвый.
    _orig_api = updater._api
    try:
        updater._api = lambda: "https://invalid.invalid.nonexistent-host-zzz"
        ok("check() offline -> None", updater.check() is None)
        ok("_manifest() offline -> None", updater._manifest() is None)
    finally:
        updater._api = _orig_api


# ── control.py (статическая проводка UI; не импортируем — тянет Tk/farm) ──
def test_control_wiring():
    print("control.py wiring:")
    src = open(os.path.join(HERE, "control.py"), encoding="utf-8").read()
    ok("DEFAULT_LINKS defined", "DEFAULT_LINKS" in src and "telegram" in src)
    ok("telegram CTA opens link", '_open_link("telegram")' in src)
    ok("no broken ✈ emoji badge", "✈" not in src)
    ok("tg CTA created", "self.tg_wrap" in src and "self.tg_btn" in src and 't("tg_btn")' in src)
    ok("tg subline created", "self.tg_sub" in src and 't("tg_sub")' in src)
    ok("grade checkbox localized", "i18n.grade_name(ru)" in src)
    ok("version label", "self.ver_lbl" in src and "_app_version" in src)
    ok("check-updates label", "self.upd_lbl" in src and "_check_updates" in src)
    ok("_open_link method", "def _open_link(self" in src)
    ok("_check_updates method", "def _check_updates(self" in src)
    ok("_check_updates_worker method", "def _check_updates_worker(self" in src)
    ok("worker uses updater.check", "updater.check()" in src and "download_and_apply" in src)
    ok("refresh wires tg_btn", 'self.tg_btn.config(text=t("tg_btn"))' in src)
    ok("refresh wires upd_lbl", 'self.upd_lbl.config(text=t("upd_check"))' in src)


# ── локализация настроек: в английском UI не должно остаться русских строк ──
def test_settings_localization():
    print("settings localization (EN):")
    import ast as _ast, i18n
    src = open(os.path.join(HERE, "control.py"), encoding="utf-8").read()
    tree = _ast.parse(src)
    HELP = {"st": [0], "_s_section": [1], "_s_hint": [1], "_s_toggle": [1, 4],
            "_s_list": [1, 3], "_s_slider": [1, 7], "_s_num": [1, 4], "_s_dropdown": [1, 5]}
    def is_cyr(s):
        return any("А" <= c <= "я" or c in "Ёё" for c in s)
    strings = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, _ast.Attribute) else (fn.id if isinstance(fn, _ast.Name) else None)
            if name in HELP:
                for idx in HELP[name]:
                    if idx < len(node.args) and isinstance(node.args[idx], _ast.Constant) \
                            and isinstance(node.args[idx].value, str) and is_cyr(node.args[idx].value):
                        strings.add(node.args[idx].value)
    # каждая строка настроек должна иметь EN-перевод в _ST
    missing = [s for s in strings if s not in i18n._ST or not i18n._ST[s].get("en-US")]
    ok(f"all {len(strings)} settings strings have EN translation", not missing)
    for s in missing[:10]:
        print("    MISSING EN:", repr(s[:50]))
    # грейды локализуются и в EN не содержат кириллицы
    _orig = i18n._lang
    try:
        i18n._lang = lambda: "en-US"
        grades = ["обычный", "необычный", "редкий", "легендарный", "бессмертный",
                  "аркана", "запредельный", "celestial", "божественный", "космический"]
        for g in grades:
            nm = i18n.grade_name(g)
            ok(f"grade {g!r} -> EN {nm!r}", nm != g and not is_cyr(nm))
    finally:
        i18n._lang = _orig


def main():
    test_config()
    test_i18n()
    test_updater()
    test_settings_localization()
    test_control_wiring()
    print()
    if _fails:
        print(f"FAILED ({len(_fails)}): " + ", ".join(_fails))
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
