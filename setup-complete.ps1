# Complete Environment Setup Script for OpusLex

param(
    [switch]$SkipPython = $false
)

$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "OpusLex Complete Environment Setup" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check Python
Write-Host "Checking Python installation..." -ForegroundColor Cyan
$pythonInstalled = $false
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK Python found: $pythonVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    # Not found
}

if (-not $pythonInstalled -and -not $SkipPython) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "Python 3.12+ Installation Required" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Python not found in PATH. Please choose:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "[1] Microsoft Store (Easiest)" -ForegroundColor Cyan
    Write-Host "    - Press Windows key, type 'Microsoft Store'" -ForegroundColor Gray
    Write-Host "    - Search for 'Python 3.12'" -ForegroundColor Gray
    Write-Host "    - Click Install" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[2] Direct Download" -ForegroundColor Cyan
    Write-Host "    - https://www.python.org/downloads/" -ForegroundColor Gray
    Write-Host "    - Download Python 3.12.7" -ForegroundColor Gray
    Write-Host "    - Run installer, CHECK 'Add Python to PATH'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[3] Skip for now" -ForegroundColor Cyan
    Write-Host "    Run: .\setup-complete.ps1 -SkipPython" -ForegroundColor Gray
    Write-Host ""

    Read-Host "Press Enter after installing Python, then close and reopen PowerShell"

    # Try again
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Python found: $pythonVersion" -ForegroundColor Green
            $pythonInstalled = $true
        }
    } catch {}

    if (-not $pythonInstalled) {
        Write-Host "ERROR: Python not found. Install it first." -ForegroundColor Red
        exit 1
    }
}

# Check Node.js
Write-Host ""
Write-Host "Checking Node.js..." -ForegroundColor Cyan
try {
    $nodeVersion = node --version
    Write-Host "OK Node: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Node.js not found" -ForegroundColor Red
    exit 1
}

# Check npm
try {
    $npmVersion = npm --version
    Write-Host "OK npm: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: npm not found" -ForegroundColor Red
    exit 1
}

# Verify frontend installations
Write-Host ""
Write-Host "Checking frontend installations..." -ForegroundColor Cyan
$frontendModules = Test-Path "$projectRoot\frontend\node_modules" -PathType Container
$frontendNextModules = Test-Path "$projectRoot\frontend-next\node_modules" -PathType Container

if ($frontendModules) {
    Write-Host "OK Frontend (Vite) ready" -ForegroundColor Green
} else {
    Write-Host "WARNING: Frontend modules missing" -ForegroundColor Yellow
}

if ($frontendNextModules) {
    Write-Host "OK Frontend-Next ready" -ForegroundColor Green
} else {
    Write-Host "WARNING: Frontend-Next modules missing" -ForegroundColor Yellow
}

# Setup Backend
if ($pythonInstalled) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Setting Up Backend" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    $backendDir = "$projectRoot\backend"
    $venvDir = "$backendDir\.venv"

    # Create venv if needed
    if (Test-Path $venvDir -PathType Container) {
        Write-Host "OK Virtual environment exists" -ForegroundColor Green
    } else {
        Write-Host "Creating virtual environment..." -ForegroundColor Cyan
        Set-Location $backendDir
        python -m venv .venv
        Write-Host "OK Virtual environment created" -ForegroundColor Green
    }

    # Activate
    Write-Host "Activating virtual environment..." -ForegroundColor Cyan
    & "$venvDir\Scripts\Activate.ps1"
    Write-Host "OK Activated" -ForegroundColor Green

    # Upgrade pip
    Write-Host "Upgrading pip..." -ForegroundColor Cyan
    python -m pip install --upgrade pip -q 2>&1 | Out-Null
    Write-Host "OK pip upgraded" -ForegroundColor Green

    # Install deps
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    Write-Host "(This may take a few minutes...)" -ForegroundColor Gray
    pip install -r requirements.txt -q 2>&1 | Out-Null
    Write-Host "OK Dependencies installed" -ForegroundColor Green
}

# Check env files
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Environment Files" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if (Test-Path "$projectRoot\backend\.env" -PathType Leaf) {
    Write-Host "OK backend\.env exists" -ForegroundColor Green
} else {
    Write-Host "ERROR: backend\.env missing" -ForegroundColor Red
}

if (Test-Path "$projectRoot\frontend\.env.local" -PathType Leaf) {
    Write-Host "OK frontend\.env.local exists" -ForegroundColor Green
} else {
    Write-Host "ERROR: frontend\.env.local missing" -ForegroundColor Red
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "[1] Edit backend\.env with your configuration" -ForegroundColor Cyan
Write-Host "    - DATABASE_URL (required)" -ForegroundColor Gray
Write-Host "    - JWT_SECRET_KEY (required)" -ForegroundColor Gray
Write-Host ""
Write-Host "[2] Start Backend (Terminal 1):" -ForegroundColor Cyan
Write-Host "    .\start-backend.ps1" -ForegroundColor Gray
Write-Host "    API: http://localhost:8000" -ForegroundColor Gray
Write-Host "    Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "[3] Start Frontend (Terminal 2):" -ForegroundColor Cyan
Write-Host "    .\start-frontend.ps1" -ForegroundColor Gray
Write-Host "    App: http://localhost:5173 (Vite)" -ForegroundColor Gray
Write-Host ""
Write-Host "Available Scripts:" -ForegroundColor Yellow
Write-Host "    .\setup-complete.ps1     Complete setup with guidance" -ForegroundColor Gray
Write-Host "    .\setup-backend.ps1      Backend setup only" -ForegroundColor Gray
Write-Host "    .\start-backend.ps1      Start FastAPI" -ForegroundColor Gray
Write-Host "    .\start-frontend.ps1     Start frontend" -ForegroundColor Gray
Write-Host ""
Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "    QUICK-START.md" -ForegroundColor Gray
Write-Host "    SETUP.md" -ForegroundColor Gray
Write-Host ""

Set-Location $projectRoot
