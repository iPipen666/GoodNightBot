@echo off
title TBH Farm TEST (1 cycle)
cd /d "d:\FOR_MYSELF\TBH_BOT"
echo ============================================================
echo  TBH FARM - ТЕСТ: один цикл, со скринами в crops\farm\
echo  Бот сам откроет CUBE, выставит Synthesis (с проверкой),
echo  переберёт типы, autofill, save, sort, сундуки.
echo  НЕ вежливый (сработает сразу) - запускай когда готов смотреть.
echo  СТОП: F12.
echo ============================================================
".venv\Scripts\python.exe" farm.py --once --shots --rude
echo.
echo --- цикл завершён, скрины в crops\farm\ ---
pause
