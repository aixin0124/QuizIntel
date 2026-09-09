param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $PSScriptRoot).Path
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$sitePackages = Join-Path $venv "Lib\site-packages"
$backendRequirements = Join-Path $root "backend\requirements.txt"
$frontend = Join-Path $root "frontend"
$envFile = Join-Path $root ".env"

Set-Location -LiteralPath $root

Write-Host "Checking project environment..."

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating Python virtual environment..."
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Install Python 3.11 or newer first."
    }
    & $pythonCommand.Source -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python virtual environment."
    }
    $Install = $true
}

$requiredPackages = @(
    "fastapi",
    "uvicorn",
    "requests",
    "dotenv",
    "multipart",
    "reportlab",
    "pytest"
)

$missingPackages = @()
foreach ($package in $requiredPackages) {
    if (-not (Test-Path -LiteralPath (Join-Path $sitePackages $package))) {
        $missingPackages += $package
    }
}

if ($missingPackages.Count -gt 0) {
    $Install = $true
}

if ($Install) {
    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install -r $backendRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "Backend dependency installation failed."
    }
}

if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination $envFile
    throw "Created .env. Fill in LLM_API_KEY, LLM_BASE_URL and LLM_MODEL, then run start.bat again."
}

$envLines = Get-Content -LiteralPath $envFile -Encoding UTF8
foreach ($name in @("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")) {
    $line = $envLines |
        Where-Object { $_ -match ("^\s*" + $name + "\s*=") } |
        Select-Object -First 1
    $value = ""
    if ($line) {
        $value = (($line -split "=", 2)[1]).Trim()
    }
    if (-not $value -or $value -match "^your_|^YOUR_|^your full|^your model|^your compatible") {
        throw "Configure $name in .env before starting the project."
    }
}

if ($Install -or -not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location -LiteralPath $frontend
    if (Test-Path -LiteralPath (Join-Path $frontend "package-lock.json")) {
        npm ci
    }
    else {
        npm install
    }
    $npmExitCode = $LASTEXITCODE
    Pop-Location
    if ($npmExitCode -ne 0) {
        throw "Frontend dependency installation failed."
    }
}

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    return $false
}

$escapedPython = $venvPython.Replace("'", "''")
$backendCommand = "& '$escapedPython' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
$backendProcess = Start-Process -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -WorkingDirectory $root `
    -ArgumentList @("-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) `
    -PassThru

$frontendCommand = "npm run dev -- --host 127.0.0.1"
$frontendProcess = Start-Process -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -WorkingDirectory $frontend `
    -ArgumentList @("-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) `
    -PassThru

$backendReady = Wait-ForUrl "http://127.0.0.1:8000/api/health"
$frontendReady = Wait-ForUrl "http://127.0.0.1:5173/"
if (-not $backendReady -or -not $frontendReady) {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw "Service startup timed out. Check Python, Node.js, and ports 8000/5173."
}

Write-Host ""
Write-Host "Project started."
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend health: http://localhost:8000/api/health"
Write-Host "Admin password: value of ADMIN_PASSWORD in .env"
