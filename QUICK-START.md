# OpusLex Quick Start Guide

## ⚡ Quick Setup (5 mins after Python is installed)

### 1. Install Python 3.12+
- **Microsoft Store**: Search "Python 3.12" → Install
- **OR** Download from https://www.python.org/downloads/
- ✅ Check "Add Python to PATH" during installation
- Restart PowerShell

### 2. Run Setup Script
```powershell
cd C:\Users\307457\Documents\project\arun\legal-compliance-research-assitant
.\setup-backend.ps1
```

### 3. Configure Environment
Edit `backend\.env` and add:
- `DATABASE_URL` - Your PostgreSQL connection string
- `JWT_SECRET_KEY` - Generate a random key or use: `your-dev-secret-key`

### 4. Start the Servers

**Terminal 1 - Backend:**
```powershell
.\start-backend.ps1
```
→ API at http://localhost:8000

**Terminal 2 - Frontend:**
```powershell
.\start-frontend.ps1
```
→ App at http://localhost:5173 (Vite) or http://localhost:3000 (Next.js)

---

## 📚 Full Documentation

See [SETUP.md](SETUP.md) for detailed instructions.

---

## 🎯 What's Ready Now

✅ Frontend (Vite + React) - Ready to run  
✅ Frontend-Next (Next.js) - Ready to run  
✅ Backend dependencies - Ready to install  
✅ Environment files - Created and configured  

⏳ Python 3.12+ - **Waiting for your installation**

---

## 🔗 Important Links

- **Backend API Docs**: http://localhost:8000/docs
- **GitHub Repo**: https://github.com/arunshrinivaas/legal-compliance-research-assitant
- **Full Setup Guide**: [SETUP.md](SETUP.md)
- **Project Status**: [qa_report.md](qa_report.md)
- **Known Issues**: [copilot_connectivity_report.md](copilot_connectivity_report.md)

---

## ✅ Checklist

- [ ] Python 3.12+ installed
- [ ] PowerShell closed and re-opened
- [ ] `.\setup-backend.ps1` completed
- [ ] `backend\.env` configured
- [ ] `./start-backend.ps1` running
- [ ] `./start-frontend.ps1` running
- [ ] Frontend loads at http://localhost:5173
- [ ] Backend API responds at http://localhost:8000/docs

---

## 💡 Tips

1. **Keep 2 terminals open**: One for backend, one for frontend
2. **Hot reload works**: Edit frontend/backend code, changes apply automatically
3. **API Documentation**: Visit http://localhost:8000/docs when backend is running
4. **Database not required initially**: Frontend works standalone
5. **Choose one frontend**: Either Vite (5173) or Next.js (3000), not both

---

**Once Python is installed, run: `.\setup-backend.ps1`**
