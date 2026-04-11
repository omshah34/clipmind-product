from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.jobs import router as jobs_router
from api.routes.upload import router as upload_router
from config import settings


app = FastAPI(title="ClipMind API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(jobs_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "prompt_version": settings.clip_prompt_version}
