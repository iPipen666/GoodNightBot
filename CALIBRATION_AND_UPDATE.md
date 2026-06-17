# Whole-bot calibration + update rollout (2026-06-16)

## Что построено (готово, офлайн+headless проверено)

**Единый реестр калибровок — `calibration.py`.** Бот теперь знает ВСЕ свои калибровки и их статус:

| id | что | файл | система координат | гейтит фичу |
|---|---|---|---|---|
| panels | кнопки панелей (stash/cube/hero/mail/settings) | offsets.json | **banner-relative (портативно)** | farm/stash/mail/merge/hop |
| cube | сетка куба + контролы мержа | calibration.json | window-fraction | merge |
| log | чтение лога RECORDS | records_calibration.json | window-fraction | log/prelock |
| chest | точки открытия сундука | chest_calibration.json | window-fraction | chest |
| portal | карта стадий (Stage hop) | portal_calibration.json | window-fraction | hop |
| settings | тогглы настроек игры | game_settings_calibration.json | window-fraction | gamesettings |

(`inv/stash/auto/panel_toggles` — легаси, читаются только `_attic` → не гейтим. `boxes_calibration.json` —
vision-тюнинг, не клик-точки → не гейтим.)

**Статус-гейт.** `calibration.status_all()/summary()/feature_status(feat)`. window-fraction валидна
только на окне своего размера (`calib_window {w,h}` / `win_rect_at_cal`, допуск 2%). Не ok → фича
**не кликает вслепую** (как `stagenav.goto` для PORTAL). banner-relative (offsets) портативна → ok при наличии.

**UI — НА ГЛАВНОМ ЭКРАНЕ, под START** (не в настройках, по фидбеку Дениса): кнопка **⚙ Calibrate now (N)**
прямо под START + строка-подсказка сколько точек не готово. Клик → отдельный экран-оверлей: по каждой
калибровке статус ✓/⚠ + кнопка `calibrate` (запускает её калибратор в консоли) + `re-check`. Кнопка на
главном зеленеет «✓ calibrated» когда всё ok. (`control._open_calibration`/`_calib_render`/`_refresh_calib_bar`.)

**Калибраторы стампят окно.** `calibrate_portal.py` и `calibrate_records.py` пишут `calib_window`
при сохранении (`calibration.json` уже несёт `win_rect_at_cal`) → после калибровки гейт даёт ok.

## Обновление существующих юзеров (EXE) — «сделай удобно»

**В клиенте (готово):** при старте панель тихо зовёт `updater.check()`; если есть подписанная новее
версия — строка версии превращается в заметную зелёную плашку **«⬆ update vX»**. Клик → диалог с
предупреждением, что новая версия требует разовой калибровки (Settings → Calibration), farm работает
сразу, hop/клик-фичи включатся после калибровки → `updater.download_and_apply` (Inno `/SILENT`).
Авто-тихая установка НЕ включена (`config.update.auto=false`) — юзер решает сам.

**Чтобы юзеры это получили (твой шаг, нужен аппрув — push/публикация = hard stop):**
1. `VERSION` ← новый номер (напр. `1.1.0`).
2. PyInstaller build (`GoodNightBot.spec` → `GoodNightBot.exe`) + Inno installer (`GoodNightBot.iss`).
3. Подписать манифест: `sig = Ed25519("version|sha256")` приватным ключом (паблик в `updater.py`).
4. Залить установщик + `latest.json {version,url,sha256,sig,notes}` на `gnb.shann.store` (pscp/plink).
   - `notes` попадёт в диалог обновления — впиши «one-time calibration required».
5. Существующие EXE-юзеры при следующем запуске увидят плашку и обновятся в один клик.

**Open-source юзеры:** `git push` (нужен твой аппрув) → они `git pull`. Сервер им latest.json новее
не отдаёт (их версия = git HEAD), плашки не будет — обновление через git, как и договорились.

## Проверка живьём (на тебе)
1. Запусти панель батником. Settings → **Calibration** — увидишь статусы (сейчас: panels ✓,
   cube «window changed», log/settings «no window», portal/chest «not calibrated»).
2. Прогони калибраторы кнопками (PORTAL, log/chest через calibrate_records, cube через calibrate.py).
3. `re-check` → строки зеленеют. Фичи включаются по мере готовности их калибровок.

## Файлы
`calibration.py` (+`test_calibration.py` 10/10), `stagenav.py` (гейт PORTAL), `control.py` (вкладка
Calibration + апдейт-плашка), `calibrate_portal.py`/`calibrate_records.py` (стамп окна). Тесты
hop-сьютов зелёные. Дефолтный count-first фарм не тронут.
