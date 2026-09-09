"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import ai_pmo, categorize, imports, issue_triage, issues, people, projects, tasks

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AI PMO API",
    version="0.1.0",
    description=(
        "Project Management OS - 通常のPJ管理に加え、隠れた課題の発見・遅延リスク分析・"
        "打ち手提案を行うAI PMOバックエンド。"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(people.router)
app.include_router(issue_triage.router)
app.include_router(issues.router)
app.include_router(ai_pmo.router)
app.include_router(categorize.router)
app.include_router(imports.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "llm": settings.llm_available}
