param(
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 3000
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Personalized Learning Agent System ===" -ForegroundColor Cyan
Write-Host "Backend Port: $BackendPort"
Write-Host "Frontend Port: $FrontendPort"
Write-Host ""

# --------------------------------------------------------
# 1. Backend: create venv
# --------------------------------------------------------
$backendDir = Join-Path $root "backend"
$venvDir = Join-Path $backendDir "venv"

if (-not (Test-Path $venvDir)) {
    Write-Host "[backend] Creating virtual environment..." -ForegroundColor Yellow
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $pythonCmd) {
        Write-Host "[ERROR] Python not found." -ForegroundColor Red
        Pause; exit 1
    }
    & $pythonCmd.Source -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] venv creation failed." -ForegroundColor Red
        Pause; exit 1
    }
    Write-Host "[backend] venv created." -ForegroundColor Green
}

# --------------------------------------------------------
# 2. Backend: install dependencies
# --------------------------------------------------------
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $backendDir "requirements.txt"

$prevEA = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $venvPython -c "import fastapi" 2>&1 | Out-Null; $exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEA
if ($exitCode -ne 0) {
    Write-Host "[backend] Installing packages from requirements.txt..." -ForegroundColor Yellow
    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] pip install failed." -ForegroundColor Red
        Pause; exit 1
    }
    Write-Host "[backend] Packages installed." -ForegroundColor Green
} else {
    Write-Host "[backend] Packages already installed." -ForegroundColor Green
}

# --------------------------------------------------------
# 3. Frontend: install npm
# --------------------------------------------------------
$frontendDir = Join-Path $root "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $nodeModules)) {
    Write-Host "[frontend] Installing npm dependencies..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] npm install failed." -ForegroundColor Red
        Pause; exit 1
    }
    Write-Host "[frontend] npm dependencies installed." -ForegroundColor Green
} else {
    Write-Host "[frontend] npm dependencies already installed." -ForegroundColor Green
}

# --------------------------------------------------------
# 4. Update vite proxy config
# --------------------------------------------------------
$viteConfig = Join-Path $frontendDir "vite.config.ts"
if (Test-Path $viteConfig) {
    $content = Get-Content $viteConfig -Raw -Encoding UTF8
    $updated = $content -replace "target: 'http://127.0.0.1:\d+'", "target: 'http://127.0.0.1:${BackendPort}'"
    if ($updated -ne $content) {
        Set-Content $viteConfig $updated -Encoding UTF8 -NoNewline
        Write-Host "[config] Frontend proxy updated -> http://127.0.0.1:${BackendPort}" -ForegroundColor Green
    }
}

# --------------------------------------------------------
# 5. Write launch scripts and spawn processes
# --------------------------------------------------------
$backendLaunchScript = @"
Set-Location -LiteralPath '$backendDir'
. '$venvDir\Scripts\Activate.ps1'
Write-Host 'Backend running at http://127.0.0.1:${BackendPort}' -ForegroundColor Green
uvicorn main:app --host 127.0.0.1 --port ${BackendPort} --reload
Pause
"@

$frontendLaunchScript = @"
Set-Location -LiteralPath '$frontendDir'
Write-Host 'Frontend running...' -ForegroundColor Green
npm run dev
Pause
"@

$tmpDir = Join-Path $root ".tmp"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$backendLaunchFile = Join-Path $tmpDir "_backend.ps1"
$frontendLaunchFile = Join-Path $tmpDir "_frontend.ps1"
$backendLaunchScript | Out-File -FilePath $backendLaunchFile -Encoding UTF8
$frontendLaunchScript | Out-File -FilePath $frontendLaunchFile -Encoding UTF8

Write-Host "[backend] Starting backend service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $backendLaunchFile
)

Start-Sleep -Seconds 1

Write-Host "[frontend] Starting frontend service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $frontendLaunchFile
)

Write-Host ""
Write-Host "Waiting for backend to start (may take 30-60s on first run due to PyTorch init)..." -ForegroundColor Yellow
$backendReady = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:${BackendPort}/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        Write-Host -NoNewline "." -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host ""
if ($backendReady) {
    Write-Host "=== Startup Complete ===" -ForegroundColor Cyan
    Write-Host "Backend:  http://localhost:${BackendPort}/docs" -ForegroundColor Green
    Write-Host "Frontend: http://localhost:${FrontendPort}" -ForegroundColor Green
} else {
    Write-Host "=== Startup: Backend may still be loading ===" -ForegroundColor Yellow
    Write-Host "Backend:  http://localhost:${BackendPort}/docs (check the backend window for state)" -ForegroundColor Yellow
    Write-Host "Frontend: http://localhost:${FrontendPort}" -ForegroundColor Green
}
Write-Host ""
Write-Host "Close the two backend/frontend windows to stop, or press any key here to exit." -ForegroundColor Gray
Pause
