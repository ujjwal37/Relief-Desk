# Start the served Relief Desk API (and the web dev server if it is not running).
# Sets only process environment. Never reads, prints or changes services/api/.env.
#   AI_MODE=auto, LOCAL_AI_ENABLED=false  -> Gemini from .env, never the local test AI
#   DEMO_MODE=true                         -> one-click demo login
#   JWT_SECRET=<random per start>          -> signs demo sessions (sessions end on restart)
param([switch]$Seed)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root 'services\api'

$listen = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listen) { Stop-Process -Id $listen.OwningProcess -Force; Start-Sleep -Seconds 2 }

$env:AI_MODE = 'auto'
$env:LOCAL_AI_ENABLED = 'false'
$env:DEMO_MODE = 'true'
$env:JWT_SECRET = 'served-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
Remove-Item Env:GOOGLE_GEMINI_BASE_URL, Env:GEMINI_BASE_URL -ErrorAction SilentlyContinue
$env:GIT_SHA = (git -C $root rev-parse --short HEAD).Trim()

Start-Process -FilePath (Join-Path $api '.venv\Scripts\python.exe') -WorkingDirectory $api `
  -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' -WindowStyle Hidden `
  -RedirectStandardOutput "$env:TEMP\api8000.log" -RedirectStandardError "$env:TEMP\api8000.err" | Out-Null
Write-Output "api started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') IST at $env:GIT_SHA"

if (-not (Get-NetTCPConnection -LocalPort 4200 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath 'cmd.exe' -WorkingDirectory $root -ArgumentList '/c', 'npx ng serve web --port 4200 --host 127.0.0.1' -WindowStyle Hidden
  Write-Output 'web dev server started on 4200'
}

$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
  Start-Sleep -Seconds 2
  try { $h = Invoke-RestMethod http://127.0.0.1:8000/api/health; $ok = $true } catch { }
}
if (-not $ok) { throw 'API did not answer /api/health within 60 s' }
if ($Seed) {
  Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/full -Headers @{ Authorization = 'Bearer demo-coordinator-token' } | Out-Null
  Write-Output "seeded $(Get-Date -Format 'HH:mm:ss') IST"
}
$h | ConvertTo-Json -Compress
