# OpusLex Development Environment Setup Guide

## Current Status ✅

### Completed
- ✅ Frontend (Vite + React) - `node_modules` installed
- ✅ Frontend-Next (Next.js 16) - `node_modules` installed  
- ✅ Environment files created (`.env`, `.env.local`)
- ✅ Setup scripts generated (PowerShell)

### Pending
- ⏳ Python 3.12+ installation
- ⏳ Backend virtual environment setup
- ⏳ Backend dependencies installation

---

## Step 1: Install Python 3.12+

### Option A: Microsoft Store (Easiest)
1. Open **Microsoft Store** app
2. Search for **"Python 3.12"** 
3. Click **Install**
4. Wait for completion
5. Close and re-open PowerShell

### Option B: Direct Download
1. Go to https://www.python.org/downloads/
2. Download **Python 3.12.7** (Windows 64-bit installer)
3. Run the installer
4. ✅ **CHECK "Add Python to PATH"** before installing
5. Click "Install Now"
6. Close and re-open PowerShell

### Verify Installation
```powershell
python --version
# Should output: Python 3.12.x
```

---

## Step 2: Setup Backend Environment

Once Python is installed, run:

```powershell
cd C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant
.\setup-backend.ps1
```

This script will:
1. Create Python virtual environment (`.venv`)
2. Install all dependencies from `requirements.txt`
3. Verify the setup

---

## Step 3: Configure Environment Variables

### Backend Configuration (`backend/.env`)

Fill in the required values:

```env
# Database - REQUIRED
DATABASE_URL=postgresql://username:password@localhost:5432/opuslex

# JWT - REQUIRED  
JWT_SECRET_KEY=your-secure-random-key-here-min-32-chars
JWT_ALGORITHM=HS256

# Copilot AI - Optional (for LLM features)
GITHUB_COPILOT_TOKEN=your-github-token

# CORS Origins - Pre-configured for local development
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# External Services - Optional
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-secret
APPLE_CLIENT_ID=your-apple-oauth-id
APPLE_CLIENT_SECRET=your-apple-oauth-secret
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_VERIFY_SERVICE_SID=your-twilio-verify-sid
```

### Frontend Configuration (`frontend/.env.local`)

```env
VITE_API_URL=http://localhost:8000/api/v1
VITE_GOOGLE_CLIENT_ID=your-google-client-id
VITE_GOOGLE_API_KEY=your-google-api-key
```

---

## Step 4: Database Setup

### Prerequisites
- PostgreSQL 13+ installed and running
- pgvector extension installed

### Initialize Database

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

---

## Step 5: Run the Application

### Terminal 1: Start Backend
```powershell
cd legal-compliance-research-assitant
.\start-backend.ps1
```
Backend runs at: http://localhost:8000  
API Docs: http://localhost:8000/docs

### Terminal 2: Start Frontend (Vite)
```powershell
cd legal-compliance-research-assitant
.\start-frontend.ps1 -Version "vite"
```
Frontend runs at: http://localhost:5173

### OR Terminal 2: Start Frontend (Next.js)
```powershell
cd legal-compliance-research-assitant
.\start-frontend.ps1 -Version "next"
```
Frontend runs at: http://localhost:3000

---

## Common Tasks

### Run Tests
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

### Type Check Frontend
```powershell
cd frontend
npx tsc --noEmit
```

### Build Frontend for Production
```powershell
cd frontend
npm run build
```

### Lint Code
```powershell
cd frontend
npm run lint
```

---

## Environment Structure

```
legal-compliance-research-assitant/
├── frontend/                 # Vite + React (lightweight)
│   ├── src/
│   ├── node_modules/        ✅ Installed
│   ├── .env.local           ✅ Created
│   └── package.json
│
├── frontend-next/            # Next.js 16 (more features)
│   ├── app/
│   ├── node_modules/        ✅ Installed
│   ├── .env.local           ✅ Created
│   └── package.json
│
├── backend/                  # FastAPI + Python
│   ├── app/
│   ├── .venv/               ⏳ To be created
│   ├── .env                 ✅ Created
│   ├── requirements.txt      
│   └── alembic/             # Database migrations
│
├── scripts/                  # Utility scripts
├── archive/                  # Archived reference code
│
├── setup-backend.ps1        ✅ Setup script
├── start-backend.ps1        ✅ Start script
├── start-frontend.ps1       ✅ Start script
└── README.md
```

---

## Troubleshooting

### Python not found after installation
- Close and re-open PowerShell/terminal
- Restart your computer if issue persists
- Verify: `python --version`

### Virtual environment activation fails
```powershell
# Allow script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try again
.\.venv\Scripts\Activate.ps1
```

### Database connection error
- Verify PostgreSQL is running
- Check `DATABASE_URL` in `backend/.env`
- Run: `psql -U postgres -c "SELECT 1"` to test connection

### Frontend won't start
- Delete `node_modules` and `package-lock.json`
- Run `npm install` again
- Clear browser cache (Ctrl+Shift+Delete)

### Port already in use
- Backend: Change port in FastAPI startup command
- Frontend: Vite will try next available port automatically

---

## Next Steps

1. ✅ Verify all installations
2. ⏳ **Install Python 3.12+** (you are here)
3. ⏳ Run `setup-backend.ps1`
4. ⏳ Configure `.env` files with your credentials
5. ⏳ Set up PostgreSQL database
6. ⏳ Run `start-backend.ps1`
7. ⏳ Run `start-frontend.ps1`

---

## Support

For issues or questions:
- Check the QA Report: `qa_report.md`
- Review Copilot Status: `copilot_connectivity_report.md`
- Check backend tests: `pytest`
- Frontend type checking: `npx tsc --noEmit`
