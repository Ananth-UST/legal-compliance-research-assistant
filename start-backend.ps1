# Start Backend Development Server

$backendDir = "C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant\backend"

Write-Host "========================================" -ForegroundColor Green
Write-Host "Starting Backend Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Set-Location $backendDir
Write-Host "Directory: $((Get-Location).Path)" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment if not already active
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Activating virtual environment..." -ForegroundColor Cyan
    & ".\.venv\Scripts\Activate.ps1"
    Write-Host ""
}

Write-Host "Starting FastAPI server..." -ForegroundColor Cyan
Write-Host "API will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API documentation: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""

fastapi dev app/main.py

Write-Host ""
Write-Host "Backend server stopped" -ForegroundColor Yellow
