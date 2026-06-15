r"""test_safety.py — юнит-тесты safety-логики мержа (аудит 2026-06-10, F16).

Покрывает то, потеря чего = безвозвратная потеря предмета у юзера:
  • policy.decide        — MERGE/LOCK/KEEP по правилам
  • farm2._lockworthy    — лог-прелок: бижу/Immortal+/hoard → лок
  • items.rank_to_tier   — порядок грейдов (Immortal=4 — порог защиты)

Тестовый раннер в проекте — НЕ pytest (его нет). Запуск:
  .\.venv\Scripts\python.exe test_safety.py     # exit 0 = всё ок, 1 = есть провал
Имена предметов берём ИЗ items_db.json динамически (не хардкодим — устойчиво к правкам БД).
"""
import json
import os
import sys

import policy
import items
import farm2

HERE = os.path.dirname(os.path.abspath(__file__))
_fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        _fails.append(name)


def _sample_names():
    """Реальные имя-аксессуар и имя-шмот из БД (для устойчивых тестов classify)."""
    db = json.load(open(os.path.join(HERE, "items_db.json"), encoding="utf-8"))["by_name"]
    acc = next((v.get("name") or k for k, v in db.items() if v.get("accessory")), None)
    gear = next((v.get("name") or k for k, v in db.items()
                 if not v.get("accessory") and v.get("type") == "gear"), None)
    return acc, gear


def test_rank_order():
    print("items.rank_to_tier — порядок грейдов:")
    check("обычный=0", items.rank_to_tier("обычный"), 0)
    check("легендарный=3", items.rank_to_tier("легендарный"), 3)
    check("бессмертный>=4 (порог лока)", items.rank_to_tier("бессмертный") >= 4, True)
    check("космический — высший", items.rank_to_tier("космический"), len(items.RANK_TIERS) - 1)


def test_policy_decide():
    print("policy.decide — решения:")
    cfg = {"legendary_tier": 3, "lock_accessory": True}
    check("бижу -> LOCK", policy.decide({"type": "accessory", "rank_tier": 0}, cfg), policy.LOCK)
    check("материал -> MERGE", policy.decide({"type": "material", "rank_tier": 9}, cfg), policy.MERGE)
    check("шмот редкий(2) -> MERGE", policy.decide({"type": "gear", "rank_tier": 2}, cfg), policy.MERGE)
    check("шмот легендарный(3) -> MERGE", policy.decide({"type": "gear", "rank_tier": 3}, cfg), policy.MERGE)
    check("шмот бессмертный(4) -> LOCK", policy.decide({"type": "gear", "rank_tier": 4}, cfg), policy.LOCK)
    check("шмот грейд неизв(-1) -> LOCK", policy.decide({"type": "gear", "rank_tier": -1}, cfg), policy.LOCK)
    check("тип None -> LOCK", policy.decide({"type": None, "rank_tier": 0}, cfg), policy.LOCK)
    check("hoard substring -> KEEP",
          policy.decide({"name": "Старый Меч Душ", "type": "gear", "rank_tier": 0},
                        {"hoard_names": ["меч душ"]}), policy.KEEP)


def test_lockworthy():
    print("farm2._lockworthy — лог-прелок:")
    acc, gear = _sample_names()
    pol = {"lock_from_tier": 4}
    if acc:
        check(f"бижу «{acc}» любой грейд -> лок", farm2._lockworthy(acc, "обычный", pol)[0], True)
    if gear:
        check(f"шмот «{gear}» легендарный -> НЕ лок", farm2._lockworthy(gear, "легендарный", pol)[0], False)
        check(f"шмот «{gear}» бессмертный -> лок", farm2._lockworthy(gear, "бессмертный", pol)[0], True)
    check("hoard substring -> лок", farm2._lockworthy("Limitless Axe", "обычный",
          {"lock_from_tier": 4, "hoard_names": ["axe"]})[0], True)
    check("имя None -> НЕ лок (грейд-гейт прикроет)", farm2._lockworthy(None, None, pol)[0], False)
    check("неизв имя без грейда -> НЕ лок", farm2._lockworthy("Zzz Qqq", None, pol)[0], False)


if __name__ == "__main__":
    test_rank_order()
    test_policy_decide()
    test_lockworthy()
    print()
    if _fails:
        print(f"❌ ПРОВАЛЕНО: {len(_fails)} -> {_fails}")
        sys.exit(1)
    print("✅ ВСЕ ТЕСТЫ ПРОШЛИ")
