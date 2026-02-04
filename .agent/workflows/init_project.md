---
description: Set up and start the project locally
---

# Initialize Project Workflow

Set up dependencies and start the project servers.

## 1. Create Project Structure

**Goal**: Set up the necessary directories and initial files.

1.  **Create Directories**:
    - `backend`, `frontend`, `.agent/rules`, `.agent/references`, `.agent/workflows`, `docs`.
2.  **Create Files**:
    - `.agent/rules/main_rule.md` (The "Rule Dispatcher" configuration).
    - Reference docs in `.agent/references/` (e.g., `fastapi.md`, `react.md`).
    - `.gitignore` and `.env.example`.
3.  **Initialize Virtual Environment**:
    - `.venv` (if Python).

## 2. Install Dependencies

**Goal**: Ensure all project dependencies are installed.

1.  **Backend**:
    - If `uv` (Python): `uv sync`
    - If `npm` (Node): `cd backend && npm install`
2.  **Frontend**:
    - `cd frontend && npm install`

## 3. Start Servers

**Goal**: Run the local development servers.

1.  **Backend**:
    - Python/FastAPI: `uv run uvicorn app.main:app --reload --port 8000`
    - Node/Express: `cd backend && npm run dev`
2.  **Frontend**:
    - `cd frontend && npm run dev`

## 3. Validate Setup

**Goal**: Confirm the application is running.

1.  **Check API**:
    - `curl -s http://localhost:8000/health`
2.  **Check Frontend**:
    - Visit `http://localhost:5173` (or configured port).
