# watchdog.ps1 — автономный сторож GoodNightBot.
# Сам поднимает панель, ловит хэнги (логи стоят / процесс мёртв), перезапускает панель,
# при деградации игры (RAM>порог или аптайм>порог) или повторном хэнге — перезапускает ИГРУ+панель,
# держит игру foreground. Всё пишет в watchdog.log. Запускается detached, переживает сессию агента.
$ErrorActionPreference = 'SilentlyContinue'
$root    = 'd:\FOR_MYSELF\TBH_BOT'
$bat     = Join-Path $root 'TBH_Autopilot.bat'
$gameExe = 'C:\Program Files (x86)\Steam\steamapps\common\TaskbarHero\TaskBarHero.exe'
$logf    = Join-Path $root 'watchdog.log'

# пороги
$HANG_BOTH_MIN  = 25    # оба лога (session+chest) стоят N мин => хэнг
$HANG_SESS_MIN  = 40    # session_log (фарм-петля) стоит N мин даже если счёт идёт => фарм-петля залипла
$GAME_RAM_MAX   = 6000  # МБ — деградация игры
$GAME_MAX_HOURS = 6     # ч — проактивный перезапуск свежей игры
$RECUR_MIN      = 90    # если хэнг повторился <N мин после рестарта панели => виновата игра

Add-Type @'
using System; using System.Runtime.InteropServices;
public class WD {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
}
'@

function Log($m) { "$((Get-Date).ToString('MM-dd HH:mm:ss')) $m" | Out-File -Append -Encoding utf8 $logf }
function GameProc { Get-Process TaskBarHero -EA SilentlyContinue }
function PanelReal { Get-Process pythonw -EA SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 50MB } }
function Foreground { $p = GameProc; if ($p) { [WD]::ShowWindow($p.MainWindowHandle,5)|Out-Null; [WD]::BringWindowToTop($p.MainWindowHandle)|Out-Null; [WD]::SetForegroundWindow($p.MainWindowHandle)|Out-Null } }
function StopPanel { Get-Process pythonw -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }; Start-Sleep 2 }
function StartPanel { Log 'start panel'; Start-Process -FilePath $bat -WorkingDirectory $root; Start-Sleep 8; Foreground; Log ("panel pids=" + ((Get-Process pythonw -EA SilentlyContinue).Id -join ',')) }
function StopGame { $g = GameProc; if ($g) { Stop-Process -Id $g.Id -Force; Log "killed game $($g.Id)"; Start-Sleep 3 } }
function DismissOffline { try { & 'd:\FOR_MYSELF\TBH_BOT\.venv\Scripts\python.exe' 'd:\FOR_MYSELF\TBH_BOT\dismiss_offline.py' 2>&1 | ForEach-Object { Log "dismiss: $_" } } catch { Log "dismiss err $_" } }
function StartGame { Log 'start game'; Start-Process $gameExe; Start-Sleep 40; Foreground; Start-Sleep 3; DismissOffline; Log "game pid=$((GameProc).Id)" }

function FrozenMins {
  $now = Get-Date
  $s = Get-ChildItem (Join-Path $root 'session_log\*.jsonl') -EA SilentlyContinue | Sort-Object LastWriteTime -Desc | Select-Object -First 1
  $c = Get-Item (Join-Path $root 'chest_audit.log') -EA SilentlyContinue
  $sAge = if ($s) { ($now - $s.LastWriteTime).TotalMinutes } else { 999 }
  $cAge = if ($c) { ($now - $c.LastWriteTime).TotalMinutes } else { 999 }
  [pscustomobject]@{ Sess = $sAge; Both = [math]::Min($sAge,$cAge) }
}

$gameStart        = (GameProc).StartTime; if (-not $gameStart) { $gameStart = Get-Date }
$lastPanelRestart = Get-Date '2000-01-01'

Log '=== WATCHDOG START ==='
while ($true) {
  try {
    # 1. игра жива?
    if (-not (GameProc)) { Log 'GAME DEAD -> restart game+panel'; StopPanel; StartGame; $gameStart = Get-Date; StartPanel; Start-Sleep 60; continue }
    # 2. панель жива?
    if (-not (PanelReal)) { Log 'PANEL DEAD -> start panel'; StopPanel; StartPanel; $lastPanelRestart = Get-Date; Start-Sleep 60; continue }
    # 3. игра деградировала? (проактивно, чтобы не доводить до хэнга)
    $g = GameProc; $gram = [math]::Round($g.WorkingSet64/1MB,0); $guph = ((Get-Date) - $gameStart).TotalHours
    if ($gram -gt $GAME_RAM_MAX -or $guph -gt $GAME_MAX_HOURS) {
      Log "GAME DEGRADED ram=$gram uph=$([math]::Round($guph,1)) -> full restart"
      StopPanel; StopGame; StartGame; $gameStart = Get-Date; StartPanel; $lastPanelRestart = Get-Date; Start-Sleep 60; continue
    }
    # 4. хэнг? оба лога стоят, или фарм-петля стоит долго
    $f = FrozenMins
    if ($f.Both -gt $HANG_BOTH_MIN -or $f.Sess -gt $HANG_SESS_MIN) {
      $recur = ((Get-Date) - $lastPanelRestart).TotalMinutes -lt $RECUR_MIN
      if ($recur) {
        Log "HANG (sess=$([math]::Round($f.Sess))m both=$([math]::Round($f.Both))m) RECURRING -> restart GAME+panel"
        StopPanel; StopGame; StartGame; $gameStart = Get-Date; StartPanel
      } else {
        Log "HANG (sess=$([math]::Round($f.Sess))m both=$([math]::Round($f.Both))m) -> restart panel"
        StopPanel; StartPanel
      }
      $lastPanelRestart = Get-Date; Start-Sleep 60; continue
    }
    # норма — держим игру впереди
    Foreground
  } catch { Log "ERR $_" }
  Start-Sleep -Seconds 60
}
