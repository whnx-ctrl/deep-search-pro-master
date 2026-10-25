param(
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$backendRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $backendRoot 'venv\Scripts\python.exe'
$logDirectory = Join-Path $backendRoot 'logs'
$logPath = Join-Path $logDirectory 'backend.log'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "未找到后端虚拟环境 Python：$pythonPath"
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Set-Location -LiteralPath $backendRoot
$env:PYTHONUNBUFFERED = '1'

$uvicornArguments = @(
    '-X', 'faulthandler',
    '-m', 'uvicorn',
    'api.server:app',
    '--host', '127.0.0.1',
    '--port', '8000',
    '--log-level', 'info'
)

if ($Reload) {
    $uvicornArguments += '--reload'
}

Write-Host "后端目录：$backendRoot"
Write-Host "运行日志：$logPath"
Write-Host "热重载：$Reload"

& $pythonPath @uvicornArguments 2>&1 | Tee-Object -FilePath $logPath -Append
$processExitCode = $LASTEXITCODE
if ($null -eq $processExitCode) {
    $processExitCode = 1
}
Write-Host "后端已退出，退出码：$processExitCode"
exit $processExitCode
