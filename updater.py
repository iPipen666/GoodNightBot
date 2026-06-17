"""updater.py — авто-обновление клиента GoodNightBot.

GET https://gnb.shann.store/latest.json -> {version, url, sha256, sig}.
sig = Ed25519-подпись строки "version|sha256" (публичный ключ вшит ниже). Если версия
новее текущей И подпись валидна И sha256 скачанного совпал — запускаем установщик. Подпись =
даже взломав сервер, нельзя подсунуть малварь.
"""
import os
import json
import time
import base64
import hashlib
import subprocess
import urllib.request

# Публичный ключ Ed25519 для проверки ПОДПИСИ ОБНОВЛЕНИЙ (не лицензия — только integrity апдейта).
PUBLIC_KEY_HEX = "8b200d441f01dfc8bcf74f1c8747d1992cb640713a65381840fe4345171b483e"  # ротирован 2026-06-09

API = "https://gnb.shann.store"     # дефолт; сервер ещё не выбран — реальный берётся из config.update.api
HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "VERSION")
CUR_VERSION = "1.0.0"


def _api():
    """Базовый URL сервера обновлений из config (update.api), иначе дефолт.
    Позволяет сменить сервер позже одной правкой config.json без перекомпиляции клиента."""
    try:
        cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
        return (cfg.get("update", {}).get("api") or API).rstrip("/")
    except Exception:
        return API


def _current():
    try:
        return open(VERSION_FILE, encoding="utf-8").read().strip()
    except Exception:
        return CUR_VERSION


def _vtuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _verify_sig(message, sig_b64u):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub.verify(base64.urlsafe_b64decode(sig_b64u + "=" * (-len(sig_b64u) % 4)), message.encode())
        return True
    except Exception:
        return False


def check():
    """Вернуть манифест обновления, если доступна новая ПОДПИСАННАЯ версия, иначе None."""
    try:
        with urllib.request.urlopen(_api() + "/latest.json", timeout=15) as r:
            m = json.load(r)
    except Exception:
        return None
    ver, url, sha, sig = m.get("version"), m.get("url"), m.get("sha256"), m.get("sig")
    if not (ver and url and sha and sig):
        return None
    if _vtuple(ver) <= _vtuple(_current()):
        return None
    if not _verify_sig(f"{ver}|{sha}", sig):
        return None                      # подпись не сошлась — игнор (защита от подмены сервера)
    return m


def download(m, on_progress=None):
    """Скачать установщик в TEMP, проверить sha256. on_progress(frac 0..1). Возвращает путь.
    Бросает при ошибке хэша/сети. Прошлый файл мог остаться ЗАЛОЧЕННЫМ (Defender / прерванная
    установка) → open(wb) дал бы «нет доступа к файлу»; удаляем, не вышло — уникальное имя по pid."""
    tmp = os.environ.get("TEMP", HERE)
    dst = os.path.join(tmp, f"GoodNightBot-{m['version']}.exe")
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError:
        dst = os.path.join(tmp, f"GoodNightBot-{m['version']}-{os.getpid()}.exe")
    with urllib.request.urlopen(m["url"], timeout=180) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        h = hashlib.sha256(); done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk); h.update(chunk); done += len(chunk)
            if on_progress and total:
                on_progress(done / total)
    if h.hexdigest() != m["sha256"]:
        os.remove(dst)
        raise ValueError("хэш не совпал — файл повреждён/подменён")
    return dst


def install(path):
    """Тихо поставить скачанный установщик поверх, ДОЖДАТЬСЯ конца. Возвращает код возврата
    (Inno ставит .py/.exe поверх даже при открытой панели — локов на них нет)."""
    flags = 0x08000000 if os.name == "nt" else 0
    return subprocess.run([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                          creationflags=flags, timeout=420).returncode


def download_and_apply(m, on_progress=None):
    """Скачать + поставить + дождаться. (ok, msg). on_progress(frac 0..1)."""
    try:
        rc = install(download(m, on_progress))
        if rc != 0:
            return False, f"установщик вернул код {rc}"
        return True, f"v{m['version']} установлено — перезапусти панель"
    except Exception as e:
        return False, f"ошибка обновления: {e}"


def auto(on_progress=None):
    """Тихая проверка+применение при старте. Возвращает (updated: bool, msg: str)."""
    m = check()
    if not m:
        return False, "обновлений нет"
    return download_and_apply(m, on_progress)


STATE_FILE = os.path.join(HERE, "update_state.json")


def _manifest():
    """Сырой манифест (нужен min_version даже когда новее нет). None при офлайне."""
    try:
        with urllib.request.urlopen(_api() + "/latest.json", timeout=10) as r:
            return json.load(r)
    except Exception:
        return None


def _grace_h():
    try:
        cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
        return float(cfg.get("update", {}).get("must_update_grace_h", 72))
    except Exception:
        return 72.0


def gate():
    """Версионный КИЛЛСВИТЧ. state: ok | update | must_update.
    must_update -> deadline (unix) = (когда ВПЕРВЫЕ увидели current<min_version) + grace.
    Клиент: state=must_update и now>deadline -> ОТКЛЮЧИТЬ фарм (баннер «обнови»). Офлайн -> не лочим."""
    m = _manifest()
    if not m:
        return {"state": "ok", "version": _current(), "deadline": None}
    cur, ver, minv = _vtuple(_current()), m.get("version"), m.get("min_version")
    if minv and cur < _vtuple(minv):
        try:
            s = json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            s = {}
        if not s.get("below_since"):
            s["below_since"] = int(time.time())
            try:
                json.dump(s, open(STATE_FILE, "w", encoding="utf-8"))
            except Exception:
                pass
        return {"state": "must_update", "version": ver,
                "deadline": int(s["below_since"] + _grace_h() * 3600)}
    if os.path.exists(STATE_FILE):              # снова валидны — сбросить отсчёт
        try:
            os.remove(STATE_FILE)
        except Exception:
            pass
    if ver and cur < _vtuple(ver):
        return {"state": "update", "version": ver, "deadline": None}
    return {"state": "ok", "version": _current(), "deadline": None}


def check_button(on_progress=None):
    """Ручная кнопка «Проверить обновление». (ok: bool, msg: str)."""
    m = check()
    if not m:
        return True, "У тебя последняя версия."
    return download_and_apply(m, on_progress)


if __name__ == "__main__":
    print("current:", _current())
    print("check:", check())
    print("gate:", gate())
