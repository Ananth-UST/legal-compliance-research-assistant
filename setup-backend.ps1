# Backend Setup Script for Windows PowerShell
# Run this after Python 3.12+ is installed

$backendDir = "C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant\backend"

Write-Host "========================================" -ForegroundColor Green
Write-Host "OpusLex Backend Setup" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Change to backend directory
Set-Location $backendDir
Write-Host "Working directory: $((Get-Location).Path)" -ForegroundColor Cyan

# Check Python
Write-Host ""
Write-Host "Checking Python installation..." -ForegroundColor Cyan
python --version

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found. Please install Python 3.12+ first." -ForegroundColor Red
    exit 1
}

# Create virtual environment
Write-Host ""
Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
python -m venv .venv

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".\\.venv\\Scripts\\Activate.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to activate virtual environment" -ForegroundColor Red
    exit 1
}

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Install dependencies
Write-Host ""
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Cyan
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Backend Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Configure your .env file with database credentials and API keys"
Write-Host "2. Run: fastapi dev app/main.py"
Write-Host ""
