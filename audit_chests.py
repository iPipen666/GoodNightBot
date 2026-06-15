r"""audit_chests.py — РАЗБОР chest_audit.log: замером (не на словах) проверить точность счёта сундуков.

Каждый засчитанный сундук бот пишет с СНИМКОМ видимых строк лога в этот момент (farm2._audit_chests).
Двойной счёт = одну и ту же лог-строку сундука засчитали в ДВУХ соседних опросах. Этот скрипт ловит
такие случаи: для каждого COUNT смотрит, была ли «опознавательная» строка сундука УЖЕ в ПРЕДЫДУЩЕМ
снимке (значит она висела и её пересчитали) → подозрение на перещёт.

Запуск:  .\.venv\Scripts\python.exe audit_chests.py
Вывод:   всего засчитано, подозрений на дубль, и сами подозрительные строки.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "chest_audit.log")


def _chest_id(key):
    """Из key события сундука вытащить опознавательный кусок (полную строку, если есть)."""
    # ключ вида 'nots|chest|normal|Obtained Common Treasure Chest. (Ele' ИЛИ '[hh:mm]|chest|normal'
    parts = (key or "").split("|", 3)
    line = parts[3] if len(parts) >= 4 else ""
    return re.sub(r"[^a-zа-я0-9]+", " ", line.lower()).strip()


def main():
    if not os.path.exists(PATH):
        print("chest_audit.log нет — запусти бота с фиксом, набей сундуков, потом сюда."); return
    blocks = []          # [(counted_keys[], snapshot_norm[])]
    cur_keys = []
    for ln in open(PATH, encoding="utf-8"):
        m = re.search(r"key=(['\"])(.*?)\1", ln)
        if "COUNT" in ln and m:
            cur_keys.append(m.group(2))
        elif ln.strip().startswith("snapshot["):
            snap = ln.split(":", 1)[1] if ":" in ln else ""
            rows = [re.sub(r"[^a-zа-я0-9]+", " ", s.lower()).strip()
                    for s in snap.split("||")]
            blocks.append((cur_keys, [r for r in rows if r]))
            cur_keys = []
    total = sum(len(k) for k, _ in blocks)
    suspects = []
    prev_snap = []
    for keys, snap in blocks:
        for k in keys:
            cid = _chest_id(k)
            # подозрение: опознавательная строка сундука была видна УЖЕ в прошлом снимке
            if cid and any(cid and cid in r or (r and r in cid) for r in prev_snap):
                suspects.append((k, cid))
        prev_snap = snap
    print(f"COUNT-блоков: {len(blocks)}  |  всего засчитано сундуков: {total}")
    print(f"подозрений на ДУБЛЬ (строка висела в прошлом снимке): {len(suspects)}")
    if total:
        print(f"доля подозрительных: {100*len(suspects)/total:.1f}%")
    for k, cid in suspects[:25]:
        print("   ⚠", repr(cid[:60]), "  ← key:", k[:50])
    if not suspects:
        print("✓ дублей не обнаружено — счёт чистый по этому замеру")


if __name__ == "__main__":
    main()
