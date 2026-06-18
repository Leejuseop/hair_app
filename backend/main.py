from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="Hair App API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    steps: list[str] | None = None


class StyleReferenceRequest(BaseModel):
    file_name: str | None = None


class GenerateRequest(BaseModel):
    scan_id: str | None = None
    style_reference_id: str | None = None


@app.post("/api/scan")
def create_scan(payload: ScanRequest) -> dict[str, Any]:
    return {
        "scan_id": str(uuid4()),
        "status": "placeholder_created",
        "steps": payload.steps or ["front", "left", "right", "hairline"],
    }


@app.post("/api/style-reference")
def create_style_reference(payload: StyleReferenceRequest) -> dict[str, Any]:
    return {
        "style_reference_id": str(uuid4()),
        "status": "placeholder_uploaded",
        "file_name": payload.file_name,
    }


@app.post("/api/generate")
def generate_result(payload: GenerateRequest) -> dict[str, Any]:
    return {
        "result_id": str(uuid4()),
        "status": "placeholder_generation_queued",
        "scan_id": payload.scan_id,
        "style_reference_id": payload.style_reference_id,
    }


@app.get("/api/result/{result_id}")
def get_result(result_id: str) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "status": "placeholder_ready",
        "image_url": None,
    }

