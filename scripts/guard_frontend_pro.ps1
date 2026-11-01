# guard_frontend_pro.ps1 — 守护 :8899 自建前端静态服务（serve_frontend_pro.py）
# 用途：进程/端口掉线时自动拉起；配合计划任务(登录自启)实现常驻。
# 互斥：若已有本守护实例在跑，直接退出，避免多会话叠加双守护。
$ErrorActionPreference = 'Continue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path (Split-Path -Parent $scriptDir) 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$log = Join-Path $logDir 'frontend_guard.log'

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    try { Add-Content -LiteralPath $log -Value $line -Encoding UTF8 } catch {}
}

# 互斥：已存在其他 guard 实例则退出
$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like '*guard_frontend_pro*' -and $_.ProcessId -ne $PID
}
if ($existing) {
    Write-Log "another guard instance running (pid=$($existing.ProcessId -join ',')) -> exit"
    exit 0
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = 'python' }
$svc = Join-Path $scriptDir 'serve_frontend_pro.py'

Write-Log "guard started (pid=$PID python=$python)"
while ($true) {
    $alive = $false
    # 1) 进程检查
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like '*serve_frontend_pro*' -and $_.ProcessId -ne $PID
    }
    if ($procs) { $alive = $true }
    # 2) 端口健康检查（进程在但服务挂同样拉起）
    if ($alive) {
        try {
            $r = Invoke-WebRequest -Uri 'http://localhost:8899/' -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ne 200) { $alive = $false }
        } catch { $alive = $false }
    }
    if (-not $alive) {
        Write-Log 'detected down -> restarting serve_frontend_pro.py'
        try {
            Start-Process -FilePath $python -ArgumentList $svc,'--port','8899' -WindowStyle Hidden
            Write-Log 'restart issued'
        } catch {
            Write-Log ("restart failed: " + $_.Exception.Message)
        }
    }
    Start-Sleep -Seconds 30
}
