"""ocr_engine.py — OCR через RapidOCR (PP-OCR ONNX): детект текстовых строк + распознавание.
Замена Tesseract — заметно точнее на мелком пиксель-арт-тексте поверх прозрачного оверлея
(«Не удалось пройти Этап 2-7» 0.96 vs Tesseract «Че удалось»). Детект сам находит все строки —
band-сегментация/мультимасштаб больше не нужны.

Модель распознавания по группе языков (config.lang_main): кириллица (рус/укр/бел) → eslav-модель
в models/ocr/eslav/; иначе дефолтная ch/en RapidOCR (латиница читается ею). Лениво, потокобезопасно.
"""
import os
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_ESLAV = os.path.join(HERE, "models", "ocr", "eslav")
_CYRILLIC_LANGS = ("ru", "uk", "be", "bg", "sr", "mk")

_ENGINE = None
_LOCK = threading.Lock()


def _ocr_lang():
    """Язык ИГРЫ для OCR (что РЕНДЕРИТ игра, не UI продукта). config.ocr_lang приоритетен; иначе
    lang_main. Для игры на русском нужен 'ru' даже если UI продукта English."""
    try:
        import json
        c = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
        return c.get("ocr_lang") or c.get("lang_main", "en-US")
    except Exception:
        return "en-US"


def _engine():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _LOCK:
        if _ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR
            lang = (_ocr_lang() or "en").split("-")[0].lower()
            rec = os.path.join(_ESLAV, "rec.onnx")
            keys = os.path.join(_ESLAV, "dict.txt")
            eng = None
            # кириллич. модель через 1.4.x-API (rec_model_path/rec_keys_path). Если не загрузилась
            # (нет модели / другая версия rapidocr) — НЕ падаем, берём дефолтную (латиница).
            if lang in _CYRILLIC_LANGS and os.path.exists(rec) and os.path.exists(keys):
                try:
                    eng = RapidOCR(rec_model_path=rec, rec_keys_path=keys)
                except Exception:
                    eng = None
            if eng is None:
                eng = RapidOCR()
            _ENGINE = eng
    return _ENGINE


def read(frame):
    """OCR кадра (np-массив, BGR как из logwatch.grab/mss). Вернуть [(text, (x0,y0,x1,y1))] в коорд.
    кадра, сверху вниз. RapidOCR ест BGR — передаём как есть."""
    a = np.asarray(frame)
    if a.ndim == 3 and a.shape[2] >= 3:
        a = np.ascontiguousarray(a[:, :, :3])
    res, _ = _engine()(a)
    out = []
    for box, txt, _score in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((txt, (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
    out.sort(key=lambda tb: tb[1][1])
    return out
