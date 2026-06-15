"""GoodNightBot — журнал сессий по датам: лут/мержи/события пишутся в session_log/<дата>.jsonl,
читаются для вкладки «Сессии» в панели."""
import os
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "session_log")


def record(kind, text):
    """Записать событие (kind: loot/merge/save/mail/event) в журнал текущей даты."""
    try:
        os.makedirs(DIR, exist_ok=True)
        rec = {"t": time.strftime("%H:%M:%S"), "kind": kind, "text": text}
        with open(os.path.join(DIR, time.strftime("%Y-%m-%d") + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def dates():
    """Список дат с журналами (новые сверху)."""
    try:
        return sorted([f[:-6] for f in os.listdir(DIR) if f.endswith(".jsonl")], reverse=True)
    except Exception:
        return []


def read(day):
    """Записи за дату -> список dict {t, kind, text}."""
    out = []
    try:
        for ln in open(os.path.join(DIR, day + ".jsonl"), encoding="utf-8"):
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    except Exception:
        pass
    return out
