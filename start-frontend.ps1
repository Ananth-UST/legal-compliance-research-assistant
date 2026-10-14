# Start Frontend Development Server
# Choose between Vite (React) or Next.js

param(
    [string]$Version = "vite"  # Options: "vite" or "next"
)

$projectRoot = "C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant"

if ($Version -eq "next") {
    $frontendDir = Join-Path $projectRoot "frontend-next"
    $port = 3000
} else {
    $frontendDir = Join-Path $projectRoot "frontend"
    $port = 5173
}

Write-Host "========================================" -ForegroundColor Green
Write-Host "Starting Frontend ($Version)" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Set-Location $frontendDir
Write-Host "Directory: $((Get-Location).Path)" -ForegroundColor Cyan
Write-Host "Port: $port" -ForegroundColor Cyan
Write-Host ""

npm run dev

Write-Host ""
Write-Host "Frontend server stopped" -ForegroundColor Yellow
