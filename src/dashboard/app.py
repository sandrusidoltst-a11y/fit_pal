"""Standalone FastAPI app for the coach dashboard API.

Deliberately separate from src/security/webapp.py: that app is gated by
InternalTokenMiddleware (the bot<->langgraph channel) which would 401 a browser
client. This app carries no auth middleware in Phase 1 (decision D1 in
docs/plans/dashboard-phase-1-foundation.md). Deployment/hosting topology is a
Phase 5 decision.
"""

from fastapi import FastAPI

from src.dashboard.routes.trainees import router as trainees_router

app = FastAPI(title="FitPal Coach Dashboard API")
app.include_router(trainees_router)


@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}
