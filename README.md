# Archived Python Reference Repo

# OpusLex: Legal & Compliance Research Assistant

OpusLex is a RAG-based AI Agent platform for legal and compliance professionals. It allows teams to investigate incidents, compare documents against compliance frameworks, and chat securely with an internal knowledge base.

## Architecture Overview
- **Frontend**: React + TypeScript + Vite + Tailwind CSS.
- **Backend**: FastAPI (Python 3.12).
- **Database**: PostgreSQL with pgvector for embeddings. ORM by SQLAlchemy + Alembic.
- **AI/LLM**: Powered by GitHub Copilot models.

## Prerequisites
- Node.js (v18+)
- Python (3.12+)
- PostgreSQL (with `pgvector` extension)
- GitHub Copilot CLI and valid license/account (required for backend LLM features)

## Backend Setup
1. `cd backend`
2. Create virtual environment: `python -m venv .venv`
3. Activate: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Configure environment: Copy `.env.example` to `.env` and fill the variables.
6. Initialize Database:
   - Ensure PostgreSQL is running.
   - Run migrations: `alembic upgrade head`
7. Start Server: `fastapi dev app/main.py` (or `uvicorn app.main:app --reload`)

## Frontend Setup
1. `cd frontend`
2. Install dependencies: `npm install`
3. Configure environment: Copy `.env.example` to `.env.local` and define `VITE_API_BASE_URL` (defaults to `http://127.0.0.1:8000`).
4. Start dev server: `npm run dev`
5. Production build: `npm run build`

## Copilot Requirement
**IMPORTANT**: The target deployment machine MUST have the GitHub Copilot CLI installed, configured, and authenticated with an active account/license. The application relies on `gh copilot` for AI model resolution.

## Integrations
- **Google Drive, Dropbox, Box, OneDrive, SharePoint**: Currently unavailable ("Coming Soon" intentionally).

## Local Development & Testing
- Backend tests: `pytest`
- Migrations check: `alembic heads` && `alembic current`
- Frontend type check: `npx tsc --noEmit`

## Known Limitations
- The Copilot connectivity layer requires a clean, authenticated environment to succeed. Tests that hit the Copilot API may fail locally if the environment lacks proper authentication.

## Credits
- **Original Project**: Created by [arunshrinivaas](https://github.com/arunshrinivaas)
- **Current Maintainer**: [Ananth-UST](https://github.com/Ananth-UST)

This is a fork/continuation of the original OpusLex project. Special thanks to the original author for the foundation and architecture.