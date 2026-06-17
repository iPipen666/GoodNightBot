# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import (collect_all, collect_data_files,
                                     collect_submodules, collect_dynamic_libs)

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# ── OCR: RapidOCR (PP-OCR ONNX) + локальная кириллическая модель (ocr_engine.py) ──
# RapidOCR держит свои дефолтные .onnx + config.yaml ВНУТРИ пакета → собрать как data-файлы.
datas += collect_data_files('rapidocr_onnxruntime')
hiddenimports += collect_submodules('rapidocr_onnxruntime')
# onnxruntime: нативные .dll/.pyd иногда не подхватываются автоматически.
binaries += collect_dynamic_libs('onnxruntime')
hiddenimports += collect_submodules('onnxruntime')
# eslav-модель (rec.onnx/dict.txt/config.json) → лежит рядом, ocr_engine.py ищет её относительно
# своего файла (HERE = _MEIPASS в бандле). Назначение должно совпасть: models/ocr/eslav.
_eslav = os.path.join(os.path.abspath(SPECPATH), 'models', 'ocr', 'eslav')
if os.path.isdir(_eslav):
    datas += [(os.path.join(_eslav, f), 'models/ocr/eslav') for f in os.listdir(_eslav)]


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GoodNightBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\FOR_MYSELF\\TBH_BOT\\icon.ico'],
)
